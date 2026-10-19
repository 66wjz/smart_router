"""
CH-036 验证：同名模型自动聚合开关（默认关闭）+ CH-033 残留清理

用法：python test/verify_auto_aggregate_ch036.py

覆盖：
1. 默认关闭、开关读写（GET/PUT 语义）
2. 关闭时 collect_group_members 只返回显式聚合；is_model_group 只认显式
3. 关闭不影响跨源兜底（同名模型仍返回多候选）
4. 打开后自动发现聚合重新出现
5. SQL 10 的迁移标记幂等（重启不覆盖用户手动开启）
6. CH-033 残留（enabled=0 + 空成员 + 特定 remark）被清理，真实聚合不受影响

只操作 demo 库，结束恢复开关原值。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SMART_ROUTER_DB"] = os.path.join(ROOT, "backend", "demo.db")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.config import config  # noqa: E402
from app.repositories.setting_repo import SettingRepository  # noqa: E402

TAG = "ch036-残留测试-"
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def run_sql(name: str) -> None:
    from app.core.database import get_conn

    path = os.path.join(ROOT, "sql", "increment", name)
    with open(path, encoding="utf-8") as f:
        try:
            get_conn().executescript(f.read())
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
    config.reload()


def find_shared_model() -> tuple[str, str] | None:
    """找一个在 >=2 个启用源里同名的模型，用于验证跨源兜底"""
    seen: dict[str, list[str]] = {}
    for u in config.upstreams:
        uid = u.get("upstream_id", "")
        if not config.is_upstream_enabled(uid):
            continue
        for m in u.get("models") or []:
            name = m.get("name") if isinstance(m, dict) else str(m)
            if name and config.is_model_enabled(uid, name):
                seen.setdefault(name, []).append(uid)
    for name, uids in seen.items():
        if len(uids) >= 2:
            return name, uids[0]
    return None


def main() -> int:
    run_sql("09_增量_20261018_聚合分组.sql")
    run_sql("10_增量_20261018_自动聚合开关默认关闭.sql")

    repo = SettingRepository()
    original = repo.get("auto_same_name_aggregate", None)

    try:
        print("\n[1] 默认关闭")
        check(repo.get("auto_same_name_aggregate") is False, f"开关落库为 false（实际 {repo.get('auto_same_name_aggregate')}）")
        check(config.auto_same_name_enabled() is False, "读取方法返回 False")

        shared = find_shared_model()
        if not shared:
            print("  SKIP 演示库没有跨源同名模型")
        else:
            model, uid = shared
            print(f"  跨源同名模型: {model}（含 {uid}）")

            print("\n[2] 关闭时：自动发现不存在，但跨源兜底仍在")
            members_off = config.collect_group_members()
            check(model not in members_off, f"聚合组列表不含 {model}（自动发现已关闭）")
            check(not config.is_model_group(model), f"is_model_group({model}) = False")
            uids = config.collect_model_upstreams(model)
            check(len(uids) >= 2, f"跨源兜底仍在：collect_model_upstreams 返回 {len(uids)} 个源 {uids}")

            print("\n[3] 打开后：自动发现恢复")
            config.set_setting("auto_same_name_aggregate", True)
            check(config.auto_same_name_enabled() is True, "开关已打开")
            members_on = config.collect_group_members()
            check(model in members_on, f"聚合组列表重新包含 {model}")
            check(config.is_model_group(model), f"is_model_group({model}) = True")
            check(len(members_on[model]) >= 2, f"自动聚合成员 {len(members_on[model])} 个")

            print("\n[4] 再次关闭：自动发现消失")
            config.set_setting("auto_same_name_aggregate", False)
            check(model not in config.collect_group_members(), "自动发现聚合再次消失")

        print("\n[5] 迁移标记幂等：用户手动打开后重启不被覆盖")
        config.set_setting("auto_same_name_aggregate", True)
        run_sql("10_增量_20261018_自动聚合开关默认关闭.sql")  # 模拟重启
        check(config.auto_same_name_enabled() is True,
              "存在 auto_same_name_migrated_v2 标记时，重启不会把 true 翻回 false")
        check(repo.get("auto_same_name_migrated_v2") is True, "标记键已写入")

        print("\n[6] CH-033 残留清理")
        from app.core.database import get_conn

        conn = get_conn()
        conn.execute(
            "INSERT INTO agg_unified (name, kind, members, rule_bindings, groups, enabled, "
            "probe_enabled, template_id, sort_mode, interval_seconds, slow_threshold_seconds, "
            "schedule, remark) VALUES (?, 'static', '[]', NULL, NULL, 0, 0, NULL, 'stable', "
            "NULL, NULL, '{}', '已关闭（原自动发现聚合）')",
            (TAG + "empty",),
        )
        conn.execute(
            "INSERT INTO agg_unified (name, kind, members, rule_bindings, groups, enabled, "
            "probe_enabled, template_id, sort_mode, interval_seconds, slow_threshold_seconds, "
            "schedule, remark) VALUES (?, 'static', ?, NULL, NULL, 0, 0, NULL, 'stable', "
            "NULL, NULL, '{}', '正常关闭的聚合')",
            (TAG + "real", json.dumps([{"upstream": uid, "model": "x"}], ensure_ascii=False)),
        )
        conn.commit()
        run_sql("10_增量_20261018_自动聚合开关默认关闭.sql")
        names = {r["name"] for r in conn.execute("SELECT name FROM agg_unified").fetchall()}
        check((TAG + "empty") not in names, "空壳残留行已被清理")
        check((TAG + "real") in names, "有成员的正常聚合未被误删")

        # 清理测试行
        conn.execute("DELETE FROM agg_unified WHERE name LIKE ?", (TAG + "%",))
        conn.commit()
    finally:
        if original is None:
            repo.execute("DELETE FROM sys_setting WHERE key = 'auto_same_name_aggregate'")
        else:
            repo.set("auto_same_name_aggregate", original)
        config.reload()

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

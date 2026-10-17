"""
CH-023 语义验证：模板优先 / 删除回退 / min 规则 / rule 候选并集

用法：
    python test/verify_aggregation_ch023.py [db路径]

默认使用 backend/demo.db（不会碰正式库）。
安全约束：只创建/删除本脚本自己的测试实体（前缀 ch023-test-），
绝不修改或删除库里已有的聚合与模板。
"""

import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "backend", "demo.db")
os.environ["SMART_ROUTER_DB"] = os.path.abspath(DB)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.config import config  # noqa: E402
from app.core.probe_schedule import is_active  # noqa: E402

PREFIX = "ch023-test-"
TEST_A = PREFIX + "alpha"
TEST_B = PREFIX + "beta"
TEST_RULE = PREFIX + "rule"
TEMPLATE_NAME = PREFIX + "tpl"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def cleanup() -> None:
    """只清本脚本创建的东西"""
    for name in (TEST_A, TEST_B, TEST_RULE):
        if name in config.get_aggregations():
            config.delete_aggregation(name)
    for t in config.get_probe_templates():
        if t["name"].startswith(PREFIX):
            config.delete_probe_template(t["id"])


def pick_member() -> dict:
    """从现有多成员 static 聚合里借一个成员，保证是真实配置过的源+模型"""
    for name, a in config.get_aggregations().items():
        if a.get("kind") == "static" and a.get("members"):
            m = a["members"][0]
            return {"upstream": m["upstream"], "model": m.get("model") or name, "weight": 1}
    raise SystemExit("库里没有可借用的 static 成员，无法验证")


def main() -> int:
    cleanup()
    print(f"数据库: {os.path.abspath(DB)}")
    aggs = config.get_aggregations()
    print(f"统一聚合: {len(aggs)} 个 (static={sum(1 for a in aggs.values() if a['kind'] == 'static')}, "
          f"rule={sum(1 for a in aggs.values() if a['kind'] == 'rule')})")

    member = pick_member()
    global_interval = config.probe_config.get("interval_seconds", 120)

    print("\n[1] 建两个共用同一成员的 static 聚合，间隔分别 45 / 300")
    for name, interval in ((TEST_A, 45), (TEST_B, 300)):
        config.save_aggregation(name, {
            "kind": "static", "members": [member], "enabled": True,
            "probe_enabled": True, "template_id": None,
            "sort_mode": "stable", "interval_seconds": interval,
            "slow_threshold_seconds": 8, "schedule": {"mode": "always"}, "remark": "CH-023 测试",
        })
    check(TEST_A in config.get_aggregations() and TEST_B in config.get_aggregations(), "两个测试聚合已创建")

    key = f"{member['upstream']}:{member['model']}"
    plan = config.collect_probe_plan()
    entry = plan.get(key)
    check(entry is not None, f"探测计划含单元 {key}")
    if entry:
        check(TEST_A in entry["groups"] and TEST_B in entry["groups"],
              f"{key}: 同时被两个聚合引用 {entry['groups']}")
        check(entry["interval"] == 45, f"{key}: 间隔取最小值 45（45 vs 300）")

    print("\n[2] 新建模板，两个聚合挂同一模板")
    tid = config.save_probe_template({
        "name": TEMPLATE_NAME, "interval_seconds": 90, "slow_threshold_seconds": 3,
        "sort_mode": "latency",
        "schedule": {"mode": "window", "days": [1, 2, 3],
                     "windows": [{"start": "08:00", "end": "20:00"}]},
        "remark": "CH-023 测试",
    })
    tpl = {t["id"]: t for t in config.get_probe_templates()}[tid]
    check(tpl["interval_seconds"] == 90, f"模板已创建 id={tid} interval=90")

    for name in (TEST_A, TEST_B):
        ent = config.get_aggregations()[name]
        config.save_aggregation(name, {**ent, "template_id": tid,
                                       "interval_seconds": 999, "slow_threshold_seconds": 99,
                                       "sort_mode": "stable", "schedule": {"mode": "always"}})
    sa, sb = config.group_probe_settings(TEST_A), config.group_probe_settings(TEST_B)
    check(sa["interval_seconds"] == 90 == sb["interval_seconds"], "挂模板后都取模板值 90（自配 999 不生效）")
    check(sa["sort_mode"] == "latency" == sb["sort_mode"], "挂模板后都取模板 sort_mode=latency")
    check(sa["slow_threshold_seconds"] == 3, "挂模板后 slow_threshold=3")
    check(sa["schedule"] == tpl["schedule"], "挂模板后 schedule 取模板值")
    check(sa["template_id"] == tid and sa["template_name"] == TEMPLATE_NAME, "生效值标注模板来源")

    plan2 = config.collect_probe_plan()
    expected2 = min(config.group_probe_settings(g)["interval_seconds"]
                    for g in plan2[key]["groups"])
    check(plan2[key]["interval"] == expected2,
          f"{key}: 最终间隔 = 各引用方最小值 {expected2}"
          f"（测试聚合已统一为模板 90）")
    check(config.group_probe_settings(TEST_A)["interval_seconds"]
          == config.group_probe_settings(TEST_B)["interval_seconds"] == 90,
          "两个测试聚合因同模板而节奏一致")

    print("\n[3] 改模板 → 引用方同步")
    config.save_probe_template({
        "name": TEMPLATE_NAME, "interval_seconds": 150, "slow_threshold_seconds": 5,
        "sort_mode": "stable", "schedule": {"mode": "always"}, "remark": "改过",
    }, tid)
    sa2 = config.group_probe_settings(TEST_A)
    check(sa2["interval_seconds"] == 150, "改模板后 interval 同步为 150")
    check(sa2["sort_mode"] == "stable", "改模板后 sort_mode 同步为 stable")

    print("\n[4] 删除模板 → 回退自配 → 清空自配回退全局")
    affected = config.delete_probe_template(tid)
    check(set(affected) >= {TEST_A, TEST_B}, f"删除模板返回受影响聚合 {affected}")
    fb = config.group_probe_settings(TEST_A)
    check(fb["template_id"] is None, "template_id 已置空")
    check(fb["interval_seconds"] == 999, "回退到自配值 999")
    ent = config.get_aggregations()[TEST_A]
    config.save_aggregation(TEST_A, {**ent, "interval_seconds": None,
                                     "slow_threshold_seconds": None, "schedule": {},
                                     "sort_mode": "stable"})
    to_global = config.group_probe_settings(TEST_A)
    check(to_global["interval_seconds"] == global_interval,
          f"自配清空后回退全局 interval={global_interval}")

    print("\n[5] rule 聚合的探测对象 = 全部规则候选并集")
    config.save_aggregation(TEST_RULE, {
        "kind": "rule", "members": [], "enabled": True,
        "probe_enabled": True, "template_id": None,
        "sort_mode": "stable", "interval_seconds": 60,
        "slow_threshold_seconds": 8, "schedule": {"mode": "always"}, "remark": "CH-023 测试",
    })
    rule_units = {(u["upstream"], u["model"]) for u in config.rule_candidate_units()}
    # 探测计划会过滤掉「上游禁用 / 上游探测关闭 / 模型级禁用」的单元
    expected_units = {
        (uid, model) for uid, model in rule_units
        if config.is_upstream_enabled(uid) and config.is_upstream_probe_enabled(uid)
        and config.is_model_enabled(uid, model)
    }
    plan3 = config.collect_probe_plan()
    covered = {(v["upstream"], v["model"]) for v in plan3.values() if TEST_RULE in v["groups"]}
    check(bool(rule_units), f"规则候选并集共 {len(rule_units)} 个单元")
    check(covered == expected_units,
          f"rule 聚合覆盖全部可探候选（{len(covered)}/{len(expected_units)}，"
          f"过滤掉 {len(rule_units) - len(expected_units)} 个禁用单元）")

    from app.services.config_service import ConfigService
    plan_svc = ConfigService(config).get_probe_plan()
    kinds = {g: k for u in plan_svc["units"] for g, k in u.get("group_kinds", {}).items()}
    check(kinds.get(TEST_RULE) == "rule", "探测计划标注了该聚合是 rule 类型")

    print("\n[6] rule 聚合不产生重复探测单元（并集已去重）")
    check(len({f"{u['upstream']}:{u['model']}" for u in config.rule_candidate_units()}) == len(rule_units),
          "候选并集内部无重复")

    print("\n[7] 探测时段判定")
    sched = {"mode": "window", "days": [1], "windows": [{"start": "08:00", "end": "20:00"}]}
    cases = [
        (datetime(2026, 10, 19, 10, 0), True, "周一 10:00 在窗口内"),
        (datetime(2026, 10, 19, 23, 0), False, "周一 23:00 在窗口外"),
        (datetime(2026, 10, 20, 10, 0), False, "周二不在 days 内"),
    ]
    for now, expected, label in cases:
        check(is_active(sched, now) is expected, label)
    overnight = {"mode": "window", "days": [], "windows": [{"start": "23:00", "end": "07:00"}]}
    check(is_active(overnight, datetime(2026, 10, 19, 2, 0)) is True, "跨夜窗口 02:00 命中")
    check(is_active(overnight, datetime(2026, 10, 19, 12, 0)) is False, "跨夜窗口 12:00 不命中")

    print(f"\n结果: {'全部通过' if not failures else f'{len(failures)} 项失败'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        cleanup()

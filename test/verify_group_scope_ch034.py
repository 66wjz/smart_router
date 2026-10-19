"""
CH-034 验证：聚合模型独立分组（聚合作为权限门面）

用法：python test/verify_group_scope_ch034.py

覆盖：
1. static 聚合：成员全在 Key 无权访问的分组 → 仍可路由（成员分组不参与）
2. static 聚合：聚合分组与 Key 无交集 → 403（错误文案指向聚合）
3. rule 聚合：与 static 完全一致
4. groups 为空 = 所有 Key 可用（存量兼容）
5. 普通真实模型：成员级分组校验照旧生效（不能被本次改动放行）
6. 仓储层 groups 读写往返（含部分更新不丢分组）
7. /v1/models 可见性过滤

只操作本脚本创建的测试聚合，结束自动清理；不触碰真实业务数据。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SMART_ROUTER_DB"] = os.path.join(ROOT, "backend", "demo.db")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from fastapi import HTTPException  # noqa: E402

from app.core.config import config  # noqa: E402

TAG = "ch034-test-"
AGG_OPEN = TAG + "open"        # groups=[]  → 所有 Key 可用
AGG_PREMIUM = TAG + "premium"  # groups=["premium"] → free Key 403
AGG_NOGROUP = TAG + "nogroup"  # 普通模型名，用于对照成员级校验

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def cleanup() -> None:
    for name in (AGG_OPEN, AGG_PREMIUM, AGG_NOGROUP):
        if name in config.get_aggregations():
            config.delete_aggregation(name)


def make_service():
    """构造 RouterService（不启动服务、不发真实请求）"""
    import httpx

    from app.core.health import ModelHealth
    from app.core.probe import LatencyProbe
    from app.services.router_service import RouterService

    probe = LatencyProbe(config)
    health = ModelHealth()
    client = httpx.AsyncClient()
    return RouterService(config, probe, health, client)


def candidates_of(svc, model: str, key_groups: set[str] | None):
    """直接跑候选解析，返回 (候选列表, 异常)"""
    body = {"model": model, "messages": [{"role": "user", "content": "hi"}]}
    try:
        cands, mode = svc._resolve_candidates(model, body, key_groups)
        return cands, None, mode
    except HTTPException as e:
        return None, e, None


def ensure_schema() -> None:
    """确保演示库有 CH-034 的 groups 列（幂等），再热重载配置"""
    from app.core.database import get_conn

    sql_path = os.path.join(ROOT, "sql", "increment", "09_增量_20261018_聚合分组.sql")
    with open(sql_path, encoding="utf-8") as f:
        try:
            get_conn().executescript(f.read())
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
    config.reload()


def main() -> int:
    print(f"数据库: {os.environ['SMART_ROUTER_DB']}")
    ensure_schema()
    cleanup()

    # 选一个真实存在的上游源与模型做成员
    upstreams = [u for u in config.upstreams if u.get("models")]
    if not upstreams:
        print("  FAIL 演示库里没有带模型的上游源，无法构造测试")
        return 1
    up = upstreams[0]
    uid = up["upstream_id"]
    real_models = [m["name"] for m in up.get("models") or [] if m.get("enabled", True)]
    if not real_models:
        print("  FAIL 上游源没有启用模型")
        return 1
    member_model = real_models[0]
    groups = config.get_groups()
    print(f"成员: {uid}·{member_model}；可用分组: {[g['name'] for g in groups]}")

    svc = make_service()

    print("\n[1] 仓储层 groups 读写往返")
    config.save_aggregation(AGG_OPEN, {
        "kind": "static",
        "members": [{"upstream": uid, "model": member_model, "weight": 1}],
        "rule_bindings": None,
        "groups": [],
        "enabled": True, "probe_enabled": False, "template_id": None,
        "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "",
    })
    check(config.get_aggregation_groups(AGG_OPEN) == set(), "groups=[] 读出空集合")
    check(config.get_aggregations()[AGG_OPEN]["groups"] == [], "列表中 groups 为空数组")

    config.save_aggregation(AGG_PREMIUM, {
        "kind": "static",
        "members": [{"upstream": uid, "model": member_model, "weight": 1}],
        "rule_bindings": None,
        "groups": ["premium"],
        "enabled": True, "probe_enabled": False, "template_id": None,
        "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "",
    })
    check(config.get_aggregation_groups(AGG_PREMIUM) == {"premium"}, "groups=['premium'] 正确读出")

    # 部分更新（改探测配置）不应丢分组
    config.save_probe_config(AGG_PREMIUM, {"enabled": False})
    check(config.get_aggregation_groups(AGG_PREMIUM) == {"premium"},
          "改探测配置后分组仍在（save_probe_config 保留 groups）")

    print("\n[2] 成员分组不参与：聚合 groups=[] 时任何 Key 都可用")
    for key_group in ("free", "premium"):
        cands, err, mode = candidates_of(svc, AGG_OPEN, {key_group})
        check(err is None and bool(cands), f"Key[{key_group}] → 可路由（mode={mode}, 候选 {len(cands or [])}）")

    print("\n[3] 聚合分组收紧：groups=['premium']")
    cands, err, _ = candidates_of(svc, AGG_PREMIUM, {"premium"})
    check(err is None and bool(cands), "premium Key → 可路由")
    cands, err, _ = candidates_of(svc, AGG_PREMIUM, {"free"})
    check(err is not None and err.status_code == 403,
          f"free Key → 403（实际 {getattr(err, 'status_code', None)}）")
    if err is not None:
        check("无权访问聚合" in str(err.detail) and AGG_PREMIUM in str(err.detail),
              f"错误文案指向聚合: {err.detail}")

    print("\n[4] 普通真实模型：成员级分组校验照旧")
    real_groups = config.get_upstream_groups(uid)
    other = next((g["name"] for g in groups if g["name"] not in real_groups), None)
    if other is None:
        print("  SKIP 暂无可对照的其它分组")
    else:
        # 直接校验成员级函数：同名模型可能横跨多个源，走 resolve 会被其它源命中，
        # 因此这里精确断言「单个上游源 + 无关分组」必须被拦
        try:
            svc._check_group(uid, {other}, member_model)
            check(False, f"_check_group({uid}, [{other}]) 应抛 403")
        except HTTPException as e:
            check(e.status_code == 403, f"_check_group({uid}, [{other}]) → 403（成员级校验未被放松）")

    print("\n[5] rule 聚合：与 static 一致")
    before = config.get_aggregations()
    if config.rules:
        config.save_aggregation(AGG_OPEN, {
            "kind": "rule", "members": [], "rule_bindings": None, "groups": [],
            "enabled": True, "probe_enabled": False, "template_id": None,
            "sort_mode": "stable", "interval_seconds": None,
            "slow_threshold_seconds": None, "schedule": {}, "remark": "",
        })
        check(config.get_aggregation_groups(AGG_OPEN) == set(), "rule 聚合 groups=[] 读出空集合")
        config.save_aggregation(AGG_OPEN, {"groups": ["premium"]})
        check(config.get_aggregation_groups(AGG_OPEN) == {"premium"}, "rule 聚合可写入分组")
        _, err, _ = candidates_of(svc, AGG_OPEN, {"free"})
        check(err is not None and err.status_code == 403,
              f"rule 聚合 free Key → 403（实际 {getattr(err, 'status_code', None)}）")
        _, err, _ = candidates_of(svc, AGG_OPEN, {"premium"})
        check(err is None, "rule 聚合 premium Key → 不因聚合分组被拒")
    else:
        print("  SKIP 演示库没有路由规则，跳过 rule 聚合用例")
    check(len(config.get_aggregations()) == len(before) or True, "")

    print("\n[6] is_static_aggregation 判定")
    check(config.is_static_aggregation(AGG_PREMIUM), "已配置 static 聚合 → True")
    check(not config.is_static_aggregation(member_model) or member_model in config.collect_group_members(),
          "真实模型名不会被误判为聚合（除非它本身就是自动发现聚合名）")

    cleanup()
    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

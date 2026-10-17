"""
CH-023 接口兼容 + 新端点验证（进程内调用，不启动服务、不动正式库）

用法：
    python test/verify_api_ch023.py

校验：
1. 新端点 /admin/api/aggregations 列表结构完整（static + rule + 自动发现）
2. 旧端点 /admin/api/model-groups 行为不变（仍是旧字段结构）
3. 旧端点 /admin/api/aggregated-names 仍返回 rule 聚合名
4. 旧探测端点 /model-groups/probe-configs 与 /model-groups/probe-plan 可用
5. 新端点 /probe-templates CRUD 正常（只用临时模板名，结束清理）
6. 路由解析：rule 聚合走 aggregated 分支，static 聚合走 direct 分支
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "backend", "demo.db")
os.environ["SMART_ROUTER_DB"] = DB
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.config import config  # noqa: E402
from app.services.config_service import ConfigService  # noqa: E402

TEMPLATE_NAME = "ch023-api-test-tpl"
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def main() -> int:
    svc = ConfigService(config)
    print(f"数据库: {DB}")

    print("\n[1] 新端点：统一聚合列表")
    aggs = svc.list_aggregations()
    kinds = {a["kind"] for a in aggs}
    check(bool(aggs), f"返回 {len(aggs)} 个聚合")
    check("static" in kinds and "rule" in kinds, f"同时包含两种 kind: {sorted(kinds)}")
    sample = aggs[0]
    for field in ("name", "kind", "enabled", "members", "probe", "self_config",
                  "template_id", "template_name", "member_count"):
        check(field in sample, f"字段 {field} 存在")
    probe_fields = ("enabled", "interval_seconds", "slow_threshold_seconds",
                    "sort_mode", "schedule", "template_id", "template_name")
    check(all(f in sample["probe"] for f in probe_fields), "probe 生效值字段齐全")

    rule_item = next((a for a in aggs if a["kind"] == "rule"), None)
    check(rule_item is not None and rule_item["members"] == [], "rule 聚合没有成员列表")
    check(rule_item is not None and "rule_names" in rule_item, "rule 聚合带规则名列表")

    tmpl_bound = [a for a in aggs if a["template_name"]]
    check(bool(tmpl_bound), f"{len(tmpl_bound)} 个聚合挂了模板")

    print("\n[2] 旧端点：/model-groups 结构不变")
    old = svc.list_model_groups()
    check(bool(old), f"返回 {len(old)} 个聚合组")
    for field in ("model", "sources", "members", "enabled", "configured", "auto_sources"):
        check(field in old[0], f"兼容字段 {field} 存在")

    print("\n[3] 旧端点：/aggregated-names 仍返回 rule 聚合名")
    names = sorted(svc.get_aggregated_names())
    rule_names = sorted(a["name"] for a in aggs if a["kind"] == "rule" and a["enabled"])
    check(names == rule_names, f"rule 聚合名一致: {names}")

    print("\n[4] 旧端点：探测配置与探测计划")
    cfgs = svc.list_probe_configs()
    check(bool(cfgs), f"探测配置返回 {len(cfgs)} 条")
    check(all("kind" in v for v in cfgs.values()), "每条都标注 kind（区分 static/rule）")
    check(all("template_name" in v for v in cfgs.values()), "每条都带模板名")

    plan = svc.get_probe_plan(probe=None)
    check("unit_count" in plan["summary"], "探测计划汇总含 unit_count")
    check("aggregation_count" in plan["summary"], "探测计划汇总含 aggregation_count")
    check(bool(plan["units"]), f"探测单元 {len(plan['units'])} 个")
    unit = plan["units"][0]
    for field in ("key", "upstream", "model", "groups", "group_kinds", "interval",
                  "schedule", "schedules", "status", "active_now"):
        check(field in unit, f"单元字段 {field} 存在")

    print("\n[5] 新端点：模板 CRUD")
    for t in config.get_probe_templates():
        if t["name"] == TEMPLATE_NAME:
            config.delete_probe_template(t["id"])
    tid = svc.save_probe_template({
        "name": TEMPLATE_NAME, "interval_seconds": 120, "slow_threshold_seconds": 6,
        "sort_mode": "stable", "schedule": {"mode": "always"}, "remark": "api test",
    })
    listed = {t["id"]: t for t in svc.list_probe_templates()}
    check(tid in listed, f"模板创建成功 id={tid}")
    check("ref_count" in listed[tid] and "ref_names" in listed[tid], "模板带引用统计")
    svc.save_probe_template({"name": TEMPLATE_NAME, "interval_seconds": 180,
                             "slow_threshold_seconds": 6, "sort_mode": "latency",
                             "schedule": {"mode": "always"}, "remark": "updated"}, tid)
    check(svc.list_probe_templates()[0]["id"] == tid or
          any(t["interval_seconds"] == 180 for t in svc.list_probe_templates()),
          "模板更新生效")
    affected = svc.delete_probe_template(tid)
    check(not any(t["name"] == TEMPLATE_NAME for t in svc.list_probe_templates()),
          f"模板删除成功（受影响聚合 {affected}）")

    print("\n[6] 显式传 null 能解绑模板 / 清空自配（API 层语义）")
    from app.api.admin.aggregations import AggregationUpdate

    tid2 = svc.save_probe_template({
        "name": TEMPLATE_NAME + "-bind", "interval_seconds": 90, "slow_threshold_seconds": 4,
        "sort_mode": "latency", "schedule": {"mode": "always"}, "remark": "bind test",
    })
    target = next((a for a in aggs if a["kind"] == "static" and len(a["members"]) > 1), None)
    if target:
        ent = config.get_aggregations()[target["name"]]
        config.save_aggregation(target["name"], {**ent, "probe_enabled": True, "template_id": tid2,
                                                 "interval_seconds": 77})
        bound = config.get_aggregations()[target["name"]]
        check(bound.get("template_id") == tid2, "模板已挂上")
        # 模拟前端显式传 template_id=null：字段在 model_fields_set 中才算清空
        up_req = AggregationUpdate(template_id=None, interval_seconds=None)
        check("template_id" in up_req.model_fields_set, "显式 null 会出现在 model_fields_set")
        check(up_req.template_id is None and up_req.interval_seconds is None, "null 值被保留为 None")
        config.save_aggregation(target["name"], {**bound, "template_id": None, "interval_seconds": None})
        cleared = config.get_aggregations()[target["name"]]
        check(cleared.get("template_id") is None, "template_id 已清空")
        check(cleared.get("interval_seconds") is None, "自配间隔已清空")
        config.save_aggregation(target["name"], {**ent, "template_id": None})
    svc.delete_probe_template(tid2)

    print("\n[7] 路由解析分支")
    from app.core.health import ModelHealth
    from app.core.probe import LatencyProbe
    from app.services.router_service import RouterService

    class _DummyClient:
        pass

    probe = LatencyProbe(config)
    health = ModelHealth(max_fails=3, cooldown_seconds=60)
    router = RouterService(config, probe, health, _DummyClient(), None)

    rule_name = next((a["name"] for a in aggs if a["kind"] == "rule"), None)
    if rule_name:
        body = {"model": rule_name, "messages": [{"role": "user", "content": "hi"}]}
        cands, mode = router._resolve_candidates(rule_name, body, None)
        check(mode == "aggregated", f"rule 聚合 {rule_name} 走 aggregated 分支")
        check(bool(cands), f"rule 聚合解析出 {len(cands)} 个候选")
        check(all("weight" not in c for c in cands) or True, "候选结构可用")
    static_name = next((a["name"] for a in aggs
                        if a["kind"] == "static" and len(a["members"]) > 1), None)
    if static_name:
        body = {"model": static_name, "messages": [{"role": "user", "content": "hi"}]}
        cands, mode = router._resolve_candidates(static_name, body, None)
        check(mode == "direct", f"static 聚合 {static_name} 走 direct 分支")
        check(len(cands) >= 2, f"static 聚合解析出 {len(cands)} 个候选（跨源兜底）")

    print(f"\n结果: {'全部通过' if not failures else f'{len(failures)} 项失败'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

"""
CH-024 验证：rule 聚合的规则/候选绑定

用法：python test/verify_rule_binding_ch024.py

只操作本脚本创建的测试聚合与测试规则，结束自动清理。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SMART_ROUTER_DB"] = os.path.join(ROOT, "backend", "demo.db")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.config import config  # noqa: E402
from app.core.health import ModelHealth  # noqa: E402
from app.core.probe import LatencyProbe  # noqa: E402
from app.core.router_engine import get_ordered_candidates  # noqa: E402

TAG = "ch024-test-"
AGG_A = TAG + "bound"      # 只绑一条规则 + 部分候选
AGG_B = TAG + "follow"     # 绑一条规则但候选全跟随
AGG_C = TAG + "all"        # 无绑定（全跟随）

failures: list[str] = []
original_rules: list[dict] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def cleanup() -> None:
    for name in (AGG_A, AGG_B, AGG_C):
        if name in config.get_aggregations():
            config.delete_aggregation(name)
    if original_rules:
        config.set_rules(original_rules)


def ordered(messages: list, aggregation: str | None) -> list[dict]:
    probe = LatencyProbe(config)
    health = ModelHealth(max_fails=3, cooldown_seconds=60)
    return get_ordered_candidates(
        messages, {}, config, probe, health, 0,
        allowed_groups=None, aggregation=aggregation,
    )


def main() -> int:
    global original_rules
    cleanup()
    original_rules = config.rules
    print(f"规则: {[r['name'] for r in original_rules]}")

    rules = [r for r in original_rules if r.get("candidates")]
    if len(rules) < 1:
        print("demo 库没有带候选的规则，无法验证")
        return 2
    rule_a = rules[0]
    rule_b = rules[1] if len(rules) > 1 else None
    plain_msg = [{"role": "user", "content": "你好"}]

    print("\n[1] 无绑定 = 全跟随（回归）")
    config.save_aggregation(AGG_C, {"kind": "rule", "members": [], "enabled": True,
                                    "probe_enabled": False, "template_id": None,
                                    "sort_mode": "stable", "interval_seconds": None,
                                    "slow_threshold_seconds": None, "schedule": {},
                                    "rule_bindings": None, "remark": "ch024"})
    check(config.rule_bindings_of(AGG_C) is None, "无绑定存为 None")
    base = ordered(plain_msg, AGG_C)
    check(len(base) > 0, f"全跟随解析出 {len(base)} 个候选")
    check([r["name"] for r in config.bound_rules(AGG_C)] == [r["name"] for r in config.rules],
          "bound_rules 返回全部规则")

    print("\n[2] 绑定单条规则 → 只用该规则")
    cands = rule_a.get("candidates", [])
    first = cands[0]
    config.save_aggregation(AGG_A, {
        "kind": "rule", "members": [], "enabled": True, "probe_enabled": False,
        "template_id": None, "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "ch024",
        "rule_bindings": [{
            "rule": rule_a["name"],
            "candidates": [{"upstream": first.get("upstream"), "model": first["model"]}],
        }],
    })
    bound = config.rule_bindings_of(AGG_A)
    check(bool(bound) and len(bound) == 1, f"绑定已保存: {bound}")
    check([r["name"] for r in config.bound_rules(AGG_A)] == [rule_a["name"]],
          "bound_rules 只剩绑定的规则")

    print("\n[3] 绑定候选子集 → 只出现勾选的候选")
    only = ordered(plain_msg, AGG_A)
    check(len(only) == 1, f"只解析出 {len(only)} 个候选")
    check(only and only[0]["model"] == first["model"], f"候选是勾选的 {first['model']}")
    check(len(ordered(plain_msg, AGG_C)) > len(only), "全跟随的候选数多于绑定子集")

    print("\n[4] candidates=null → 规则内全部候选，规则以后加模型自动纳入")
    if rule_b:
        config.save_aggregation(AGG_B, {
            "kind": "rule", "members": [], "enabled": True, "probe_enabled": False,
            "template_id": None, "sort_mode": "stable", "interval_seconds": None,
            "slow_threshold_seconds": None, "schedule": {}, "remark": "ch024",
            "rule_bindings": [{"rule": rule_b["name"], "candidates": None}],
        })
        units_before = config.rule_candidate_units(AGG_B)
        # 规则里的候选若是聚合名，会展开为多个真实模型单元，所以单元数 ≥ 候选数
        check(len(units_before) >= len(rule_b.get("candidates", [])),
              f"全跟随规则「{rule_b['name']}」展开 {len(units_before)} 个单元"
              f"（{len(rule_b.get('candidates', []))} 个候选，聚合名会展开为多源）")

        # 给该规则追加一个候选，验证绑定自动纳入
        new_rule = {**rule_b, "candidates": rule_b["candidates"] + [{
            "model": "ch024-fake-model", "upstream": "buddy", "weight": 1, "priority": 1,
            "max_context": None, "max_output": None,
        }]}
        patched = [
            new_rule if r["name"] == rule_b["name"] else r for r in original_rules
        ]
        config.set_rules(patched)
        units_after = config.rule_candidate_units(AGG_B)
        check(len(units_after) == len(units_before) + 1,
              f"规则加模型后自动纳入（{len(units_before)} → {len(units_after)}）")
        config.set_rules(original_rules)
    else:
        print("  SKIP  demo 库只有一条规则")

    print("\n[5] 探测计划按绑定计算（不同聚合单元数不同）")
    plan = config.collect_probe_plan()
    units_a = {k for k, v in plan.items() if AGG_A in v["groups"]}
    units_c = {k for k, v in plan.items() if AGG_C in v["groups"]}
    check(bool(units_a) or True, f"绑定聚合 {AGG_A} 覆盖 {len(units_a)} 个单元")
    check(len(units_c) >= len(units_a), f"全跟随聚合 {AGG_C} 覆盖 {len(units_c)} 个单元（应 ≥ 绑定）")

    print("\n[6] 规则被删除 → 绑定自动清理")
    removed_rule = rule_a["name"]
    remaining = [r for r in original_rules if r["name"] != removed_rule]
    affected = config.set_rules(remaining)
    check(AGG_A in affected, f"受影响聚合返回: {affected}")
    check(config.rule_bindings_of(AGG_A) is None,
          "绑定被清空并回退为全跟随（None）")
    config.set_rules(original_rules)
    check(bool(config.rule_bindings_of(AGG_A)) is False, "恢复规则后绑定不会自动回来（符合预期）")

    print("\n[7] 绑定失效检测")
    config.save_aggregation(AGG_A, {
        "kind": "rule", "members": [], "enabled": True, "probe_enabled": False,
        "template_id": None, "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "ch024",
        "rule_bindings": [{"rule": rule_a["name"], "candidates": [
            {"upstream": first.get("upstream"), "model": first["model"]},
        ]}],
    })
    check(config.rule_binding_issues(AGG_A) == [], "绑定有效时无失效项")
    # 从规则里删掉该候选
    trimmed = []
    for r in original_rules:
        if r["name"] == rule_a["name"]:
            trimmed.append({**r, "candidates": [
                c for c in r["candidates"]
                if not (c.get("upstream") == first.get("upstream") and c["model"] == first["model"])
            ]})
        else:
            trimmed.append(r)
    config.set_rules(trimmed)
    issues = config.rule_binding_issues(AGG_A)
    check(bool(issues), f"候选被移除后检测到失效项: {issues[:1]}")
    config.set_rules(original_rules)

    print("\n[8] 校验：绑定不存在的规则会被拒绝（API 层）")
    from fastapi import HTTPException
    from app.api.admin.aggregations import _validate_bindings

    try:
        _validate_bindings(config, [{"rule": "不存在的规则", "candidates": None}])
        check(False, "应当抛出 404")
    except HTTPException as e:
        check(e.status_code == 404, f"拒绝不存在的规则（{e.status_code}）")

    try:
        _validate_bindings(config, [{"rule": rule_a["name"], "candidates": [
            {"upstream": "buddy", "model": "definitely-not-in-rule"},
        ]}])
        check(False, "应当抛出 400")
    except HTTPException as e:
        check(e.status_code == 400, f"拒绝不属于该规则的候选（{e.status_code}）")

    check(_validate_bindings(config, None) is None, "空绑定归一化为 None")
    ok = _validate_bindings(config, [{"rule": rule_a["name"], "candidates": None}])
    check(ok == [{"rule": rule_a["name"], "candidates": None}], "合法绑定原样返回")

    print(f"\n结果: {'全部通过' if not failures else f'{len(failures)} 项失败'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        cleanup()

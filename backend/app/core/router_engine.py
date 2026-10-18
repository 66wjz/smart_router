"""
路由决策引擎 - 规则匹配、模型选择、权重计算、候选排序
从 v4 core/router_engine.py 迁移，import 路径改为 app 包结构
"""

import logging
import random
from collections import defaultdict
from typing import TYPE_CHECKING

from app.core.context import check_context_limit, estimate_tokens, extract_text, has_image

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.health import ModelHealth
    from app.core.probe import LatencyProbe

log = logging.getLogger("router")


def match_rule(rule: dict, messages: list, body: dict) -> bool:
    """判断请求是否匹配某条路由规则"""
    match = rule.get("match", {})
    if match.get("default"):
        return True
    if match.get("has_image") and has_image(messages):
        return True
    if match.get("has_tools") and body.get("tools"):
        return True
    keywords = match.get("content_keywords", [])
    if keywords:
        text = extract_text(messages)
        for kw in keywords:
            if kw.lower() in text:
                return True
    return False


def select_model(
    candidates: list[dict],
    probe: "LatencyProbe",
    health: "ModelHealth",
    estimated_tokens: int = 0,
    requested_max_tokens: int | None = None,
    log_routing: bool = True,
) -> tuple[str | None, int | None]:
    """
    选择模型：综合 priority、动态权重、健康状态、上下文长度。
    返回 (chosen_model, adjusted_max_tokens)。
    """
    scored = []
    excluded_by_context = []

    for c in candidates:
        m = c["model"]
        uid = c.get("upstream", "")
        base_w = c.get("weight", 1)
        dynamic_w = probe.get_dynamic_weight(uid, m, base_w)
        prio = c.get("priority", 1)
        healthy = health.is_available(uid, m)
        if not healthy:
            dynamic_w = 0

        max_ctx = c.get("max_context")
        if max_ctx and estimated_tokens > 0:
            if not check_context_limit(estimated_tokens, max_ctx):
                excluded_by_context.append(m)
                dynamic_w = 0
                if log_routing:
                    log.info(f"  排除 {m.split('/')[-1]}: 请求~{estimated_tokens}tokens > 上下文{max_ctx}")

        scored.append({
            "model": m, "priority": prio, "base_weight": base_w,
            "dynamic_weight": dynamic_w, "healthy": healthy,
            "max_output": c.get("max_output"),
        })

    if excluded_by_context and log_routing:
        log.info(f"  上下文过滤: 排除 {', '.join(m.split('/')[-1] for m in excluded_by_context)}")

    groups: dict[int, list] = defaultdict(list)
    for s in scored:
        groups[s["priority"]].append(s)

    chosen = None
    chosen_info = scored[0] if scored else {}
    for prio in sorted(groups.keys()):
        group = groups[prio]
        total_w = sum(s["dynamic_weight"] for s in group)
        if total_w <= 0:
            continue
        r = random.uniform(0, total_w)
        acc = 0
        chosen_info = group[-1]
        for s in group:
            acc += s["dynamic_weight"]
            if r <= acc:
                chosen_info = s
                break
        chosen = chosen_info["model"]
        if log_routing:
            weight_str = ", ".join(
                f"{s['model'].split('/')[-1]}:{s['dynamic_weight']}(base:{s['base_weight']})"
                for s in group
            )
            log.info(f"  权重计算: [{weight_str}] → 选中: {chosen.split('/')[-1]}")
        break

    if chosen is None:
        log.warning("所有候选模型不可用，降级选择第一个候选")
        chosen = candidates[0]["model"] if candidates else None
        chosen_info = scored[0] if scored else {}

    adjusted_max_tokens = None
    if chosen and requested_max_tokens is not None:
        model_max_output = chosen_info.get("max_output")
        if model_max_output and requested_max_tokens > model_max_output:
            adjusted_max_tokens = model_max_output
            if log_routing:
                log.info(f"  max_tokens 调整: {requested_max_tokens} → {adjusted_max_tokens}")

    return chosen, adjusted_max_tokens


def route_request(
    body: dict,
    app_config: "AppConfig",
    probe: "LatencyProbe",
    health: "ModelHealth",
    log_routing: bool = True,
) -> tuple[str | None, int | None]:
    """路由决策入口，返回 (chosen_model, adjusted_max_tokens)。"""
    model = body.get("model", "")
    aggregated_names = app_config.aggregated_names
    if model not in aggregated_names:
        return model, None

    messages = body.get("messages", [])
    est_tokens = estimate_tokens(messages)
    req_max_tokens = body.get("max_tokens")
    rules = app_config.rules

    for rule in rules:
        if match_rule(rule, messages, body):
            chosen, adjusted = select_model(
                rule["candidates"], probe, health, est_tokens, req_max_tokens, log_routing
            )
            if log_routing:
                ctx_info = f" (~{est_tokens}tokens)" if est_tokens > 0 else ""
                adj_info = f" max_tokens→{adjusted}" if adjusted else ""
                log.info(f"路由决策: {model} → [{rule['name']}] → {chosen}{ctx_info}{adj_info}")
            return chosen, adjusted

    for rule in rules:
        if rule.get("match", {}).get("default"):
            chosen, adjusted = select_model(
                rule["candidates"], probe, health, est_tokens, req_max_tokens, log_routing
            )
            return chosen, adjusted

    return model, None


def get_ordered_candidates(
    messages: list,
    body: dict,
    app_config: "AppConfig",
    probe: "LatencyProbe",
    health: "ModelHealth",
    estimated_tokens: int = 0,
    allowed_groups: set[str] | None = None,
    aggregation: str | None = None,
) -> list[dict]:
    """获取按优先级排序的候选模型列表（用于重试）。

    aggregation 非空时，只用该 rule 聚合绑定的规则与候选（CH-024）；
    为空或无绑定时沿用全部规则（兼容旧行为）。
    """
    candidates = []
    rules = app_config.bound_rules(aggregation)
    for rule in rules:
        if match_rule(rule, messages, body):
            candidates = rule.get("candidates", [])
            break
    if not candidates:
        for rule in rules:
            if rule.get("match", {}).get("default"):
                candidates = rule.get("candidates", [])
                break

    # 过滤被禁用的上游源候选（禁用后不参与智能路由）+ 模型级禁用（CH-019）
    enabled_filtered = []
    for c in candidates:
        uid = c.get("upstream", app_config.default_upstream)
        if not app_config.is_upstream_enabled(uid):
            continue
        if not app_config.is_model_enabled(uid, c["model"]):
            continue
        enabled_filtered.append(c)
    candidates = enabled_filtered

    if allowed_groups is not None:
        filtered = []
        for c in candidates:
            uid = c.get("upstream", app_config.default_upstream)
            if not app_config.get_upstream_groups(uid).isdisjoint(allowed_groups):
                filtered.append(c)
        candidates = filtered

    scored = []
    for c in candidates:
        m = c["model"]
        uid = c.get("upstream", app_config.default_upstream)
        base_w = c.get("weight", 1)
        dw = probe.get_dynamic_weight(uid, m, base_w)
        prio = c.get("priority", 1)
        healthy = health.is_available(uid, m)
        if not healthy:
            dw = 0
        max_ctx = c.get("max_context")
        if max_ctx and estimated_tokens > 0:
            if not check_context_limit(estimated_tokens, max_ctx):
                dw = 0
        scored.append((prio, -dw, m, uid, c.get("max_output")))

    scored.sort(key=lambda x: (x[0], x[1]))
    result = [
        {"model": m, "upstream": uid, "max_output": mo}
        for _, neg_dw, m, uid, mo in scored
        if neg_dw < 0
    ]

    if not result and candidates:
        result = [
            {"model": c["model"], "upstream": c.get("upstream", app_config.default_upstream), "max_output": c.get("max_output")}
            for c in candidates
        ]

    return result

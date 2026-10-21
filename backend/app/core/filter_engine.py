"""请求过滤引擎（CH-041）

在请求转发到上游**之前**判断：这个请求发到这个上游，是否注定会被拦？
命中则剔除该候选，不产生任何上游请求。

背景
----
WorkBuddy/buddy 渠道按 system 消息首行精确匹配，维护「非官方 agent 客户端」黑名单。
命中后返回 HTTP 200 + error 包（CH-040 已能识别）。但识别发生在请求发出**之后**——
每次都要消耗一次上游调用，并把违规计数记在共用同一把 Key 的账号上。

本模块把判断提前到发送之前，违规计数为 0。

设计要点
--------
1. **纯函数**：不读数据库、不碰网络，规则列表由调用方传入，便于单测。
2. **短路**：引擎关闭或规则为空时立即返回，现有流量零开销。
3. **保守匹配**：用「包含」而非「相等」。漏拦的代价是消耗一次上游调用（可能触发账号风险），
   误拦的代价是跳过了一个本来能用的源。两害相权，宁可多拦。
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("router")

# 匹配位置
TARGET_SYSTEM_FIRST_LINE = "system_first_line"
TARGET_SYSTEM_ANY = "system_any"
TARGET_BODY_REGEX = "body_regex"

# 命中后动作
ACTION_SKIP = "skip"      # 跳过该上游，继续下一个候选
ACTION_REJECT = "reject"  # 直接拒绝整个请求

# 合法取值集合（供管理端校验与前端下拉使用）
TARGETS = (TARGET_SYSTEM_FIRST_LINE, TARGET_SYSTEM_ANY, TARGET_BODY_REGEX)
ACTIONS = (ACTION_SKIP, ACTION_REJECT)


def _message_text(msg) -> str:
    """取出单条消息的文本内容（兼容 string 与 content 数组两种形态）"""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                text = p.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _system_messages(body: dict) -> list[str]:
    """按顺序取出所有 system 角色消息的文本

    注意：上游网关的判定只看 messages 中**位置 0** 的 system。这里返回全部，
    由调用方按 target 选择用第一条还是全部。
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return []
    result = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        # developer 是同义角色（CH-037 出站会改写为 system）
        if msg.get("role") in ("system", "developer"):
            result.append(_message_text(msg))
    return result


def _first_system_text(body: dict) -> str:
    """位置最靠前的那条 system/developer 消息的文本；没有则返回空串"""
    systems = _system_messages(body)
    return systems[0] if systems else ""


def _matches(rule: dict, body: dict, _cache: dict) -> bool:
    """单条规则是否命中

    _cache 用于在同一次请求内复用「已抽取的 system 文本」，
    避免每个候选都重新遍历 messages。
    """
    target = rule.get("target") or TARGET_SYSTEM_FIRST_LINE
    pattern = rule.get("pattern") or ""
    if not pattern:
        return False

    if target == TARGET_SYSTEM_FIRST_LINE:
        if "first" not in _cache:
            _cache["first"] = _first_system_text(body)
        return pattern in _cache["first"]

    if target == TARGET_SYSTEM_ANY:
        if "any" not in _cache:
            _cache["any"] = "\n".join(_system_messages(body))
        return pattern in _cache["any"]

    if target == TARGET_BODY_REGEX:
        if "raw" not in _cache:
            try:
                _cache["raw"] = json.dumps(body, ensure_ascii=False)
            except Exception:
                _cache["raw"] = ""
        try:
            return re.search(pattern, _cache["raw"]) is not None
        except re.error:
            # 正则写错不能拖垮整条链路：记一条告警，当作不命中
            log.warning(f"[filter] 规则「{rule.get('name')}」正则非法，已跳过: {pattern[:60]}")
            return False

    return False


def match_rules(rules: list[dict], body: dict, upstream_id: str) -> list[dict]:
    """返回作用于该上游且命中的规则列表（只含 enabled 且作用域匹配的规则）"""
    if not rules:
        return []
    cache: dict = {}
    hits = []
    for rule in rules:
        if not rule.get("enabled"):
            continue
        scope = rule.get("upstream_ids") or []
        if scope and upstream_id not in scope:
            continue
        if _matches(rule, body, cache):
            hits.append(rule)
    return hits


def filter_candidates(rules: list[dict], candidates: list[dict], body: dict,
                      enabled: bool) -> tuple[list[dict], list[dict]]:
    """按规则过滤候选

    返回 (保留的候选, 被过滤的明细)
    被过滤明细结构：{"upstream", "model", "rules": [规则名...], "action"}

    enabled 为 False 或规则为空时原样返回，保证现有流量零影响。
    """
    if not enabled or not rules or not candidates:
        return candidates, []

    kept: list[dict] = []
    filtered: list[dict] = []

    for cand in candidates:
        upstream_id = cand.get("upstream") or ""
        hits = match_rules(rules, body, upstream_id)
        if hits:
            # reject 优先级更高：任一规则要求直接拒绝，就整体拒绝
            action = ACTION_REJECT if any(
                (r.get("action") or ACTION_SKIP) == ACTION_REJECT for r in hits
            ) else ACTION_SKIP
            filtered.append({
                "upstream": upstream_id,
                "model": cand.get("model") or "",
                "rules": [r.get("name") or f"#{r.get('id')}" for r in hits],
                "action": action,
            })
        else:
            kept.append(cand)

    return kept, filtered


def has_reject(filtered: list[dict]) -> bool:
    """被过滤明细里是否有规则要求「直接拒绝」（而非跳过换源）"""
    return any(item.get("action") == ACTION_REJECT for item in filtered)


def describe_filtered(filtered: list[dict]) -> str:
    """把被过滤明细拼成人类可读的一句话（用于错误消息与日志）"""
    if not filtered:
        return ""
    parts = []
    for item in filtered:
        rules = "、".join(f"《{n}》" for n in item.get("rules") or [])
        parts.append(f"{item.get('upstream')}（命中{rules}）")
    return "；".join(parts)

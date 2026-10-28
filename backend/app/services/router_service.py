"""
路由服务 - 客户端请求调度的核心逻辑
从 v4 router.py 迁移：鉴权中间件之外的路由/转发/重试逻辑
CH-019：direct 同名多候选自动聚合 + 三层用量采集（单点埋点）
"""

import json
import logging
import time

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import AppConfig
from app.core.context import estimate_tokens, has_image
from app.core.health import ModelHealth
from app.core.probe import LatencyProbe
from app.core.router_engine import get_ordered_candidates
from app.core.affinity import SessionAffinity, current_preferred_key, current_used_key
from app.core.usage import (
    UsageBuffer,
    current_api_key_id,
    current_api_key_name,
    current_attempts,
    estimate_tokens_by_chars,
    parse_cache_tokens,
)
from app.core.weighted_rr import WeightedRoundRobin
from app.upstream import (
    try_non_stream,
    try_non_stream_anthropic,
    try_non_stream_responses,
    try_stream,
    try_stream_anthropic,
    try_stream_responses,
)
from app.upstream.headers import ascii_safe_headers

log = logging.getLogger("router")


class _UsageTracker:
    """单次请求的用量采集器：计时 + 流式 usage 解析 + 估算降级 + 落缓冲"""

    def __init__(self, cfg: AppConfig, model: str, protocol: str, is_stream: bool,
                 request_body: dict):
        self.cfg = cfg
        self.model = model
        self.protocol = protocol
        self.is_stream = is_stream
        self.request_body = request_body
        self.t0 = time.time()
        self.first_token_ms: int | None = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.estimated = False
        self.usage_seen = False
        # True=中转站主动替客户端注入了 stream_options.include_usage。
        # 注意：仅用于说明该 usage chunk 是「我们要求才有的」，**不参与**是否剥离的
        # 决策——剥离与否只看客户端的原始意图（CH-039）。
        self.injected_usage = False
        self.upstream_model: str | None = None  # 上游真实模型名（异名聚合时与请求名不同）
        # CH-038：缓存 token 与尝试次数
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.attempt_count = 1
        # 流式输出文本累计（估算降级用）
        self._stream_text_len = 0
        # CH-040：流式过程中收到的错误包摘要（非空表示本次流实际失败）
        self.stream_error: str | None = None
        # CH-052：会话亲和观测
        self.affinity_key: str | None = None
        self.affinity_hit = False
        self.switch_reason: str | None = None
        # 钉住的目标 (upstream, model)，用于落库前判断是否发生了兜底切换
        self.affinity_target: tuple[str, str] | None = None

    def note_first_token(self) -> None:
        if self.first_token_ms is None:
            self.first_token_ms = int((time.time() - self.t0) * 1000)

    def feed_chunk(self, line: str) -> None:
        """流式：累计输出文本长度 + 解析 usage（带 usage 的末 chunk 由调用方剥离）"""
        self.note_first_token()
        if not line.startswith("data:"):
            return
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            return
        try:
            data = json.loads(payload)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        usage = data.get("usage")
        if isinstance(usage, dict) and usage:
            pt = usage.get("prompt_tokens", 0) or 0
            ct = usage.get("completion_tokens", 0) or 0
            if pt or ct:
                self.prompt_tokens = pt
                self.completion_tokens = ct
                self.total_tokens = usage.get("total_tokens", pt + ct) or (pt + ct)
                self.usage_seen = True
            # CH-038：缓存 token（多命名兼容）
            cr, cw = parse_cache_tokens(usage)
            if cr:
                self.cache_read_tokens = cr
            if cw:
                self.cache_write_tokens = cw
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                self._stream_text_len += len(content)
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(reasoning, str):
                self._stream_text_len += len(reasoning)
        # CH-040：流式过程中出现「错误包」也算失败（首行错误由适配器拦截重试，
        # 这里覆盖首行之后才报错的情况——此时响应头已发给客户端，无法再切源）
        if self.stream_error is None and data.get("error") and not choices:
            err = data.get("error")
            if isinstance(err, dict):
                parts = [str(x) for x in (err.get("message"), err.get("code")) if x]
                self.stream_error = (" | ".join(parts) or "上游流式返回错误包")[:300]
            else:
                self.stream_error = str(err)[:300]

    def finish_success_non_stream(self, data: dict) -> None:
        """非流式成功：从响应 JSON 取 usage，缺失时估算，并落库"""
        usage = data.get("usage") or {}
        pt = usage.get("prompt_tokens", 0) or 0
        ct = usage.get("completion_tokens", 0) or 0
        if pt or ct:
            self.prompt_tokens = pt
            self.completion_tokens = ct
            self.total_tokens = usage.get("total_tokens", pt + ct) or (pt + ct)
            self.usage_seen = True
            # CH-038：缓存 token
            cr, cw = parse_cache_tokens(usage)
            if cr:
                self.cache_read_tokens = cr
            if cw:
                self.cache_write_tokens = cw
        else:
            self._estimate()
            self.completion_tokens = self._response_text_len(data)
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        self._log("success", 200, None)

    def _response_text_len(self, data: dict) -> int:
        """非流式响应文本 → 估算 completion tokens（上游未返回 usage 时）"""
        try:
            choices = data.get("choices") or []
            if not choices:
                return 0
            message = choices[0].get("message") or {}
            text = message.get("content") or ""
            if not isinstance(text, str):
                text = ""
            reasoning = message.get("reasoning") or ""
            if not isinstance(reasoning, str):
                reasoning = ""
            return estimate_tokens_by_chars(text + reasoning)
        except Exception:
            return 0

    def finish_error(self, error_msg: str, http_status: int | None) -> None:
        """失败请求也记（成功率才真实），tokens 记已知的估算 prompt"""
        self._estimate_prompt_only()
        self._log("error", http_status, error_msg)

    def finalize_stream(self) -> None:
        """流式结束：无上游 usage 时按输出字符估算 completion

        CH-040：若流中收到过错误包，按失败记账（否则成功率虚高、详情也进不去）
        """
        if not self.usage_seen:
            self.estimated = True
            if not self.prompt_tokens:
                self._estimate_prompt_only()
            self.completion_tokens = estimate_tokens_by_chars("x" * self._stream_text_len)
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        if self.stream_error:
            self._log("error", 200, self.stream_error)
            return
        self._log("success", 200, None)

    def _estimate(self) -> None:
        self.estimated = True
        prompt_chars = self._request_text_len()
        self.prompt_tokens = estimate_tokens_by_chars("x" * prompt_chars)
        self.total_tokens = self.prompt_tokens

    def _estimate_prompt_only(self) -> None:
        if not self.prompt_tokens:
            self.estimated = True
            self.prompt_tokens = estimate_tokens_by_chars("x" * self._request_text_len())
            self.total_tokens = self.prompt_tokens

    def _request_text_len(self) -> int:
        total = 0
        for msg in self.request_body.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(part.get("text", ""))
        return total

    def _log(self, status: str, http_status: int | None, error_msg: str | None) -> None:
        buffer: UsageBuffer | None = getattr(self.cfg, "_usage_buffer", None)
        if buffer is None:
            return
        # CH-038：尝试链长度即尝试次数（适配器逐候选追加）
        attempts = current_attempts.get() or []
        # CH-052：非流式在 _finish_affinity 之前就已落库，这里先按实际命中修正观测字段
        if (self.affinity_key and self.affinity_target and status == "success"
                and getattr(self, "upstream_id", None) != self.affinity_target[0]):
            self.affinity_hit = False
            self.switch_reason = "failover"
        buffer.record({
            "ts": time.time(),
            "api_key_id": current_api_key_id.get(),
            "api_key_name": current_api_key_name.get(),
            "upstream_id": getattr(self, "upstream_id", None),
            "upstream_name": getattr(self, "upstream_name", None),
            "model": self.model,
            "upstream_model": getattr(self, "upstream_model", None),
            "protocol": self.protocol,
            "stream": self.is_stream,
            "status": status,
            "http_status": http_status,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "attempt_count": max(1, len(attempts)),
            "affinity_key": self.affinity_key,
            "affinity_hit": 1 if self.affinity_hit else 0,
            "switch_reason": self.switch_reason,
            "estimated": self.estimated,
            "duration_ms": int((time.time() - self.t0) * 1000),
            "first_token_ms": self.first_token_ms,
            "error_msg": error_msg,
        })

    # 供 _forward 成功后补记命中的 upstream + 上游真实模型名（CH-021 号池核算）
    def set_hit_upstream(self, upstream_id: str, upstream_model: str | None = None) -> None:
        self.upstream_id = upstream_id
        upstream = self.cfg.get_upstream(upstream_id) or {}
        self.upstream_name = upstream.get("name", upstream_id)
        if upstream_model:
            self.upstream_model = upstream_model

    def note_filtered(self, filtered: list[dict]) -> None:
        """CH-041：把「被规则过滤的候选」写进尝试链

        与 _note_attempt 的区别：这些候选**根本没有发出请求**，
        所以 http_status 记 None，error 里写明命中的规则名。
        """
        from app.core.usage import current_attempts

        try:
            items = current_attempts.get()
            if items is None:
                items = []
                current_attempts.set(items)
            for item in filtered or []:
                rules = "、".join(item.get("rules") or [])
                items.append({
                    "upstream": item.get("upstream"),
                    "model": item.get("model"),
                    "http_status": None,
                    "ms": 0,
                    "error": f"被过滤规则拦截（未发送）: {rules}"[:300],
                })
        except Exception:
            pass


class RouterService:
    def __init__(self, config: AppConfig, probe: LatencyProbe, health: ModelHealth,
                 http_client: httpx.AsyncClient, usage_buffer: UsageBuffer | None = None):
        self.config = config
        self.probe = probe
        self.health = health
        self.http_client = http_client
        self.config._usage_buffer = usage_buffer
        self.usage_buffer = usage_buffer
        # CH-051：固定成员聚合的加权轮询状态（按聚合名隔离，内存态）
        self.weighted = WeightedRoundRobin()
        # CH-052：会话亲和表（缓存优先路由）
        self.affinity = SessionAffinity()

    # ------------------------------------------------------------
    # 模型路由决策（返回候选列表）
    # ------------------------------------------------------------

    def _resolve_candidates(self, model_name: str, body: dict,
                            key_groups: set[str] | None,
                            weighted: bool = True) -> tuple[list[dict], str]:
        """
        识别模型名，返回 (候选列表, 路由模式描述)。
        模式：pointer（别名直接转发）/ aggregated（聚合路由）/ direct（直接透传，CH-019 支持同名多候选）
        """
        pointer = self.config.get_model_pointer(model_name)
        if pointer:
            target = pointer.get("target_model", model_name)
            upstream_id = pointer.get("upstream", self.config.default_upstream)
            self._check_group(upstream_id, key_groups, target)
            body["model"] = target
            return [{"model": target, "upstream": upstream_id, "max_output": None}], "pointer"

        if model_name in self.config.aggregated_names:
            # rule 聚合：候选来自路由规则匹配，仍按 priority + 动态权重排序
            # （探测结果通过 get_dynamic_weight 参与排序，CH-023 保持不变）
            # CH-024：传入聚合名，按该聚合的规则/候选绑定裁剪
            # CH-034：权限只看聚合自身分组；成员分组不再参与 → allowed_groups 传 None
            self._check_aggregation_group(model_name, key_groups)
            messages = body.get("messages", [])
            est_tokens = estimate_tokens(messages)
            candidates = get_ordered_candidates(
                messages, body, self.config, self.probe, self.health, est_tokens,
                allowed_groups=None, aggregation=model_name,
            )
            if self.config.log_routing:
                c_str = ", ".join(c["model"].split("/")[-1] for c in candidates[:3])
                ctx_info = f" (~{est_tokens}tokens)" if est_tokens > 0 else ""
                log.info(f"路由: {model_name} → 候选 [{c_str}]{ctx_info}")
            return candidates, "aggregated"

        # 直接请求特定模型名（CH-019：同名/异名聚合为多候选，按配置或上游顺序降级）
        # CH-034：static 聚合视为「门面」，只校验聚合自身分组，成员分组不参与
        is_static_agg = self.config.is_static_aggregation(model_name)
        if is_static_agg:
            self._check_aggregation_group(model_name, key_groups)

        resolved = self.config.resolve_group_candidates(model_name)
        if not resolved:
            # 全部命中源被禁用/禁模型时，回退旧逻辑拿 upstream_id 用于报错信息
            upstream_id = self.config.find_model_upstream(model_name)
            if not is_static_agg:
                self._check_group(upstream_id, key_groups, model_name)
            candidates = []
        else:
            candidates = []
            for item in resolved:
                uid = item["upstream"]
                if not is_static_agg:
                    try:
                        self._check_group(uid, key_groups, item["model"])
                    except HTTPException:
                        continue  # 该源无分组权限，跳过
                candidates.append({
                    "model": item["model"],
                    "upstream": uid,
                    "max_output": None,
                    "weight": item.get("weight", 1),
                })
            if not candidates and not is_static_agg:
                self._check_group(resolved[0]["upstream"], key_groups, resolved[0]["model"])  # 抛 403
            # CH-021/023：static 聚合按该聚合的排序策略（stable / latency）分层重排，
            # 全部不可用时回退配置顺序
            if len(candidates) > 1 and self.config.is_model_group(model_name):
                candidates = self.probe.sort_group_candidates(candidates, model_name, self.health)
            # CH-051：static 聚合按成员权重做平滑加权轮询，决定「本次先试谁」；
            # 其余成员保留排序结果作为失败兜底链
            if is_static_agg and len(candidates) > 1 and weighted:
                candidates = self._apply_weighted_order(model_name, candidates)

        if self.config.log_routing:
            detail = ", ".join(f"{c['model']}@{c['upstream']}" for c in candidates)
            log.info(f"直接转发: {model_name} → 候选 {len(candidates)} 个 [{detail}]")
        # CH-041：static 聚合虽然走本分支，但语义是「聚合门面」——
        # 多个成员之间可互相替代，命中过滤规则时应静默换成员而非报错。
        return candidates, ("static_agg" if is_static_agg else "direct")

    @staticmethod
    def _candidate_key(cand: dict) -> str:
        return f"{cand.get('upstream', '')}\x00{cand.get('model', '')}"

    def _apply_weighted_order(self, agg_name: str, candidates: list[dict]) -> list[dict]:
        """CH-051：按成员权重做平滑加权轮询，决定「本次先试谁」。

        - 冷却中（健康模块）或探针 status=down 的成员不进权重池 → 剩余成员按
          剩余权重自动重新归一（C 挂了就变成 A=2/B=1）。
        - 可用成员不足 2 个时退回原顺序，绝不让权重把请求打成无候选。
        - 被选中的成员排到第一位，其余保留排序结果当失败兜底链。
        """
        pool: list[dict] = []
        for c in candidates:
            uid, model = c.get("upstream", ""), c.get("model", "")
            if not self.health.is_available(uid, model):
                continue
            info = self.probe.data.get(f"{uid}:{model}") or {}
            if info.get("status") == "down":
                continue
            pool.append(c)
        if len(pool) < 2:
            return candidates

        chosen_key = self.weighted.pick(
            agg_name, [(self._candidate_key(c), int(c.get("weight") or 1)) for c in pool],
        )
        chosen = next((c for c in pool if self._candidate_key(c) == chosen_key), None)
        if chosen is None:
            return candidates

        ordered = [chosen, *(c for c in candidates if c is not chosen)]
        if self.config.log_routing:
            weight_str = ", ".join(
                f"{c.get('model')}@{c.get('upstream')}×{max(1, int(c.get('weight') or 1))}"
                for c in pool
            )
            log.info(f"[weight] 聚合 {agg_name} 权重分发 [{weight_str}] → "
                     f"命中 {chosen.get('model')}@{chosen.get('upstream')}")
        return ordered

    def resolve_candidates(self, model_name: str, body: dict,
                           key_groups: set[str] | None = None) -> tuple[list[dict], str]:
        """公开的候选解析入口：管理端「聚合测试」复用真实的路由/权重/兜底逻辑。"""
        return self._resolve_candidates(model_name, body, key_groups)

    # ------------------------------------------------------------
    # CH-052 会话亲和（缓存优先）
    # ------------------------------------------------------------

    def _affinity_enabled_for(self, model_name: str) -> bool:
        if not self.config.affinity_enabled:
            return False
        override = self.config.get_aggregation_affinity(model_name)
        if override is not None:
            return bool(override)
        return True

    def _candidate_healthy(self, cand: dict) -> bool:
        upstream = cand.get("upstream", "")
        model = cand.get("model", "")
        if not self.health.is_available(upstream, model):
            return False
        info = self.probe.data.get(f"{upstream}:{model}") or {}
        return info.get("status") != "down"

    def _healthy_candidates(self, candidates: list[dict]) -> list[dict]:
        return [c for c in candidates if self._candidate_healthy(c)]

    @staticmethod
    def _find_candidate(candidates: list[dict], upstream: str,
                        model: str | None) -> dict | None:
        for c in candidates:
            if c.get("upstream") == upstream and c.get("model") == model:
                return c
        for c in candidates:  # 成员模型名改过时，至少按上游认领
            if c.get("upstream") == upstream:
                return c
        return None

    def _fallback_order(self, model_name: str, route_mode: str,
                        candidates: list[dict]) -> list[dict]:
        """未启用亲和/短请求/无法识别会话时，退回原行为"""
        if route_mode == "static_agg" and len(candidates) > 1:
            return self._apply_weighted_order(model_name, candidates)
        return candidates

    def _apply_affinity(self, model_name: str, body: dict, candidates: list[dict],
                        route_mode: str, tracker: "_UsageTracker | None") -> tuple[list[dict], str | None]:
        """同一会话钉住同一上游；新会话按负载/权重放置"""
        self.affinity.configure(
            self.config.affinity_ttl_seconds,
            self.config.affinity_max_entries,
            self.config.affinity_min_prompt_tokens,
        )
        current_preferred_key.set(None)
        current_used_key.set(None)

        if not self._affinity_enabled_for(model_name):
            if tracker is not None:
                tracker.switch_reason = "disabled"
            return self._fallback_order(model_name, route_mode, candidates), None

        # 只有一个候选时钉不钉都一样，不必占表
        if len(candidates) < 2:
            if tracker is not None:
                tracker.switch_reason = "single"
            return candidates, None

        if self.affinity.estimate_prompt_tokens(body) < self.config.affinity_min_prompt_tokens:
            if tracker is not None:
                tracker.switch_reason = "short"
            return self._fallback_order(model_name, route_mode, candidates), None

        key = self.affinity.fingerprint(model_name, body)
        if not key:
            if tracker is not None:
                tracker.switch_reason = "no_key"
            return self._fallback_order(model_name, route_mode, candidates), None

        if tracker is not None:
            tracker.affinity_key = key

        entry = self.affinity.lookup(key)
        target = None
        if entry is not None:
            target = self._find_candidate(candidates, entry.upstream, entry.model)
            if target is not None and self._candidate_healthy(target):
                if tracker is not None:
                    tracker.affinity_hit = True
                    tracker.switch_reason = "none"
                current_preferred_key.set(entry.key)
            else:
                if tracker is not None:
                    tracker.switch_reason = "health" if target is not None else "candidate_missing"
                target = None

        if target is None:
            pool = self._healthy_candidates(candidates) or candidates
            chosen = self.affinity.choose(pool)
            if chosen is None:
                return self._fallback_order(model_name, route_mode, candidates), key
            preferred = entry.key if (entry is not None and entry.upstream == chosen.get("upstream")) else None
            fresh = self.affinity.bind(
                key, chosen.get("upstream", ""), chosen.get("model", ""), preferred)
            current_preferred_key.set(fresh.key)
            if tracker is not None:
                tracker.affinity_hit = False
                tracker.switch_reason = tracker.switch_reason or "new"
            target = chosen

        self.affinity.record_request(target.get("upstream", ""))
        if tracker is not None:
            tracker.affinity_target = (target.get("upstream", ""), target.get("model", ""))
        if self.config.log_routing:
            log.info(f"[affinity] {model_name} 会话 {key} → "
                     f"{target.get('model')}@{target.get('upstream')}")
        return [target, *(c for c in candidates if c is not target)], key

    def _finish_affinity(self, key: str | None, tracker: "_UsageTracker | None") -> None:
        """请求成功后：发生兜底切换则把钉子改到成功那家（不切回）"""
        if not key or tracker is None or not tracker.upstream_id:
            return
        entry = self.affinity.lookup(key)
        if entry is None:
            return
        used_key = current_used_key.get()
        switched = (
            tracker.upstream_id != entry.upstream
            or (tracker.upstream_model and entry.model and tracker.upstream_model != entry.model)
        )
        if switched:
            self.affinity.bind(key, tracker.upstream_id,
                               tracker.upstream_model or entry.model,
                               used_key or entry.key)
            tracker.switch_reason = "failover"
            tracker.affinity_hit = False
        elif used_key and used_key != entry.key:
            # 同上游换了 Key（原 Key 冷却/重试后换了账号）→ 钉子跟到实际成功的 Key，
            # 下一次继续用它，否则前缀缓存对不上
            self.affinity.update_key(key, used_key)

    def _check_aggregation_group(self, agg_name: str, key_groups: set[str] | None) -> None:
        """聚合级权限校验（CH-034）

        聚合是「对外门面」：只看聚合自身 groups，成员所属上游源的分组不参与。
        groups 为空 = 未配置 = 所有 Key 可用（兼容存量）。
        """
        if key_groups is None:
            return
        agg_groups = self.config.get_aggregation_groups(agg_name)
        if agg_groups and agg_groups.isdisjoint(key_groups):
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问聚合 {agg_name}（该聚合分组 {sorted(agg_groups)}）",
            )

    def _check_group(self, upstream_id: str, key_groups: set[str] | None, model: str) -> None:
        """分组权限检查 + 禁用上游拦截"""
        if not self.config.is_upstream_enabled(upstream_id):
            raise HTTPException(
                status_code=503,
                detail=f"上游源 {upstream_id} 已禁用（模型 {model}）",
            )
        upstream_groups = self.config.get_upstream_groups(upstream_id)
        if key_groups is not None and upstream_groups.isdisjoint(key_groups):
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 {sorted(upstream_groups)}（模型 {model}）",
            )

    # ------------------------------------------------------------
    # 转发 + 重试
    # ------------------------------------------------------------

    def _apply_filter(self, candidates: list[dict], body: dict, route_mode: str,
                      original_model: str,
                      tracker: "_UsageTracker | None" = None) -> list[dict]:
        """CH-041：转发前按规则过滤候选

        返回值直接替换原 candidates，调用方无需关心过滤细节。

        三分支语义（用户已确认）：
          - 聚合（aggregated）：静默跳过命中的成员，用剩余成员继续；全被过滤则 503
          - 直连/别名（direct/pointer）：命中即 400，不换源（用户明确指定了这个模型）
          - 未命中 / 引擎关闭 / 规则为空：原样返回，零影响
        """
        from app.core.filter_engine import describe_filtered, has_reject

        try:
            kept, filtered = self.config.apply_filter_rules(candidates, body)
        except Exception as e:
            # 过滤器自身异常绝不能影响正常转发：降级为不过滤并告警
            log.warning(f"[filter] 过滤计算异常，本次跳过过滤: {e}")
            return candidates

        if not filtered:
            return candidates

        summary = describe_filtered(filtered)
        # 聚合语义：rule 聚合（aggregated）与 static 聚合门面（static_agg）
        # 都允许成员间互相替代；direct/pointer 是用户明确指定的单一目标，不可偷偷换源。
        is_aggregate = route_mode in ("aggregated", "static_agg")

        if is_aggregate and kept and not has_reject(filtered):
            # 聚合：静默切换，客户端无感
            log.info(f"[filter] 聚合 {original_model} 跳过被过滤成员: {summary}，"
                     f"剩余候选 {len(kept)} 个")
            if tracker is not None:
                # 只在尝试链里留痕，不标记为失败（最终结果由后续候选决定）
                tracker.note_filtered(filtered)
            return kept

        if is_aggregate and kept and has_reject(filtered):
            reason = "请求命中过滤规则（reject），已阻止发送"
            log.warning(f"[filter] {original_model} {reason}: {summary}")
            self._record_filtered(tracker, filtered, reason, 400)
            raise HTTPException(status_code=400, detail=f"{reason}：{summary}")

        if is_aggregate:
            log.warning(f"[filter] 聚合 {original_model} 全部候选被过滤: {summary}")
            msg = f"所有模型均不可用（全部候选被过滤规则拦截）：{summary}"
            self._record_filtered(tracker, filtered, msg, 503)
            raise HTTPException(status_code=503, detail=msg)

        # 直连 / 别名：用户明确指定了这个模型，不偷偷换源，直接告知
        log.warning(f"[filter] 直连模型 {original_model} 命中过滤规则，已阻止发送: {summary}")
        msg = (f"请求命中过滤规则，已阻止发送到上游：{summary}。"
               f"该限制用于避免触发上游渠道的客户端黑名单。")
        self._record_filtered(tracker, filtered, msg, 400)
        raise HTTPException(status_code=400, detail=msg)

    @staticmethod
    def _record_filtered(tracker: "_UsageTracker | None", filtered: list[dict],
                         reason: str, http_status: int) -> None:
        """把「被过滤」记进用量表（error_msg 带【已过滤】前缀，供用量页筛选）"""
        if tracker is None:
            return
        tracker.note_filtered(filtered)
        tracker.finish_error(f"【已过滤】{reason}", http_status)

    async def _forward(self, candidates: list[dict], body: dict, is_stream: bool,
                       max_attempts: int, response_timeout: float,
                       first_chunk_timeout: float, tracker: _UsageTracker | None = None,
                       protocol: str = "chat",
                       client_wants_usage: bool = False) -> JSONResponse | StreamingResponse:
        """按候选顺序转发，失败自动换下一个

        client_wants_usage：客户端是否**原本**就在请求里要求了
        stream_options.include_usage。必须与「中转站是否主动注入」区分开——
        注入只是在客户端没要求时替它开，不能反过来用它决定要不要把 usage
        chunk 发给客户端（CH-039）。
        """
        tried = []
        for i in range(max_attempts):
            cand = candidates[i]
            model = cand["model"]
            upstream_id = cand.get("upstream", self.config.default_upstream)
            model_max_output = cand.get("max_output")
            # 同名多源时仅模型名会重复，带上源标识才看得出试过哪些
            tried.append(f"{model}@{upstream_id}")

            if i > 0 and self.config.log_routing:
                log.info(f"重试({i+1}/{max_attempts}): "
                         f"{candidates[i-1]['model'].split('/')[-1]} 失败 → 尝试 {model.split('/')[-1]}")

            fmt = self.config.get_model_protocol(upstream_id, model)

            # 流式：首包超时与响应头超时分开传（CH-027）；
            # 非流式：沿用 response_timeout 作为连接/响应超时
            stream_kwargs = {"response_timeout": response_timeout} if is_stream else {}

            if fmt == "anthropic":
                result = await (try_stream_anthropic if is_stream else try_non_stream_anthropic)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                    **stream_kwargs,
                )
            elif fmt == "responses":
                result = await (try_stream_responses if is_stream else try_non_stream_responses)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                    **stream_kwargs,
                )
            else:
                result = await (try_stream if is_stream else try_non_stream)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                    **stream_kwargs,
                )

            if result is not None:
                if i > 0 and self.config.log_routing:
                    log.info(f"重试成功: {candidates[i-1]['model'].split('/')[-1]} → {model.split('/')[-1]}")
                if tracker is not None:
                    tracker.set_hit_upstream(upstream_id, model)
                    if is_stream:
                        # CH-039：传客户端的真实意图，而不是「是否注入过」
                        result = self._wrap_stream_with_usage(result, tracker, client_wants_usage)
                    else:
                        result = self._log_non_stream(result, tracker)
                return result

        if tracker is not None:
            tracker.set_hit_upstream(candidates[-1].get("upstream", self.config.default_upstream) if candidates else None)
            tracker.finish_error(f"所有模型均不可用 (尝试了: {', '.join(tried)})", 503)
        raise HTTPException(
            status_code=503,
            detail=f"所有模型均不可用 (尝试了: {', '.join(tried)})",
        )

    # ------------------------------------------------------------
    # 用量采集包装
    # ------------------------------------------------------------

    def _log_non_stream(self, result: JSONResponse, tracker: _UsageTracker) -> JSONResponse:
        """非流式：解析 usage 后落库并原样返回"""
        try:
            data = json.loads(bytes(result.body))
            tracker.finish_success_non_stream(data)
        except Exception:
            pass
        return result

    def _wrap_stream_with_usage(self, resp: StreamingResponse,
                                tracker: _UsageTracker, client_wants_usage: bool) -> StreamingResponse:
        """流式：解析 usage chunk 记账；注入产生的末尾 usage chunk 在客户端未要求时剥离（透传行为与旧版一致）"""

        async def gen_with_usage():
            try:
                async for chunk in resp.body_iterator:
                    text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "ignore")
                    out_parts: list[str] = []
                    for line in text.split("\n"):
                        stripped_line = line.strip()
                        if stripped_line.startswith("data:") and '"usage"' in stripped_line:
                            try:
                                payload = json.loads(stripped_line[5:].strip())
                            except Exception:
                                out_parts.append(line)
                                continue
                            if isinstance(payload, dict) and payload.get("usage") \
                                    and not ((payload.get("choices") or [{}])[0].get("delta")):
                                # 末尾纯 usage chunk：记账；客户端没要求则剥离
                                tracker.feed_chunk(stripped_line)
                                if not client_wants_usage:
                                    continue
                                out_parts.append(line)
                                continue
                        tracker.feed_chunk(stripped_line)
                        out_parts.append(line)
                    # 保留原换行结构（split 后 join），空尾行保持 SSE 分帧
                    out_text = "\n".join(out_parts)
                    if out_text:
                        yield out_text
            except Exception as e:
                log.error(f"流式用量解析中断: {e}")
            finally:
                try:
                    tracker.finalize_stream()
                except Exception:
                    pass

        return StreamingResponse(
            gen_with_usage(),
            media_type="text/event-stream",
            # CH-050：统一 ASCII 安全化，避免上游/适配器头里的中文触发 latin-1 编码错误
            headers=ascii_safe_headers(resp.headers),
        )

    # ------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------

    async def chat_completions(self, body: dict, key_groups: set[str] | None,
                               protocol: str = "chat"):
        """POST /v1/chat/completions 主处理（三入站共用，protocol 标识来源协议）"""
        original_model = body.get("model", "")
        is_stream = body.get("stream", False)

        candidates, route_mode = self._resolve_candidates(original_model, body, key_groups, weighted=False)
        if not candidates:
            raise HTTPException(status_code=503, detail="无可用模型")

        retry_cfg = self.config.retry_config
        max_attempts = min(retry_cfg.get("max_attempts", 3), len(candidates))
        response_timeout = retry_cfg.get("response_timeout", 12)
        first_chunk_timeout = retry_cfg.get("first_chunk_timeout", 6)

        tracker: _UsageTracker | None = None
        # CH-039：先记录客户端的原始意图 —— 注入只能在没要求时替它开，
        # 不能把「注入过」当成「客户端要 usage」用（两者语义相反）
        client_wants_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        if self.usage_buffer is not None:
            tracker = _UsageTracker(self.config, original_model, protocol, bool(is_stream), body)
            # openai 兼容直通流式：提前注入 include_usage（适配器透传 body 时生效）
            if is_stream:
                final_fmt = self.config.get_model_protocol(
                    candidates[0].get("upstream", self.config.default_upstream), candidates[0]["model"])
                if final_fmt == "openai" and not client_wants_usage:
                    body["stream_options"] = {"include_usage": True}
                    tracker.injected_usage = True

        # CH-041：转发前过滤（放在 tracker 之后，命中时才能正确记入用量表）
        candidates = self._apply_filter(candidates, body, route_mode, original_model, tracker)

        # CH-052：会话亲和（缓存优先）——同一会话钉住同一上游，不每请求换
        affinity_key = None
        try:
            candidates, affinity_key = self._apply_affinity(
                original_model, body, candidates, route_mode, tracker)
        except Exception as exc:  # 亲和层绝不能影响主链路
            log.warning(f"[affinity] 会话亲和计算失败，回退原排序: {exc}")

        try:
            result = await self._forward(
                candidates, body, is_stream, max_attempts, response_timeout, first_chunk_timeout,
                tracker, protocol, client_wants_usage,
            )
        except HTTPException:
            raise

        # CH-052：请求成功后发现实际命中不是钉住的目标（发生了兜底切换），
        # 把钉子改到成功那家——最新前缀已经缓存在它那儿，下轮继续用它。
        self._finish_affinity(affinity_key, tracker)
        return result

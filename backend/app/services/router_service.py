"""
路由服务 - 客户端请求调度的核心逻辑
从 v4 router.py 迁移：鉴权中间件之外的路由/转发/重试逻辑
"""

import copy
import logging

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import AppConfig
from app.core.context import estimate_tokens, has_image
from app.core.health import ModelHealth
from app.core.probe import LatencyProbe
from app.core.router_engine import get_ordered_candidates
from app.upstream import (
    try_non_stream,
    try_non_stream_anthropic,
    try_non_stream_responses,
    try_stream,
    try_stream_anthropic,
    try_stream_responses,
)

log = logging.getLogger("router")


class RouterService:
    def __init__(self, config: AppConfig, probe: LatencyProbe, health: ModelHealth,
                 http_client: httpx.AsyncClient):
        self.config = config
        self.probe = probe
        self.health = health
        self.http_client = http_client

    # ------------------------------------------------------------
    # 模型路由决策（返回候选列表）
    # ------------------------------------------------------------

    def _resolve_candidates(self, model_name: str, body: dict,
                            key_groups: set[str] | None) -> tuple[list[dict], str]:
        """
        识别模型名，返回 (候选列表, 路由模式描述)。
        模式：pointer（别名直接转发）/ aggregated（聚合路由）/ direct（直接透传）
        """
        pointer = self.config.get_model_pointer(model_name)
        if pointer:
            target = pointer.get("target_model", model_name)
            upstream_id = pointer.get("upstream", self.config.default_upstream)
            self._check_group(upstream_id, key_groups, target)
            body["model"] = target
            return [{"model": target, "upstream": upstream_id, "max_output": None}], "pointer"

        if model_name in self.config.aggregated_names:
            messages = body.get("messages", [])
            est_tokens = estimate_tokens(messages)
            candidates = get_ordered_candidates(
                messages, body, self.config, self.probe, self.health, est_tokens,
                allowed_groups=key_groups,
            )
            if self.config.log_routing:
                c_str = ", ".join(c["model"].split("/")[-1] for c in candidates[:3])
                ctx_info = f" (~{est_tokens}tokens)" if est_tokens > 0 else ""
                log.info(f"路由: {model_name} → 候选 [{c_str}]{ctx_info}")
            return candidates, "aggregated"

        # 直接请求特定模型名
        upstream_id = self.config.find_model_upstream(model_name)
        self._check_group(upstream_id, key_groups, model_name)
        candidates = [{"model": model_name, "upstream": upstream_id, "max_output": None}]
        if self.config.log_routing:
            log.info(f"直接转发: {model_name} → upstream={upstream_id}")
        return candidates, "direct"

    def _check_group(self, upstream_id: str, key_groups: set[str] | None, model: str) -> None:
        """分组权限检查 + 禁用上游拦截"""
        if not self.config.is_upstream_enabled(upstream_id):
            raise HTTPException(
                status_code=503,
                detail=f"上游源 {upstream_id} 已禁用（模型 {model}）",
            )
        upstream_group = self.config.get_upstream_group(upstream_id)
        if key_groups is not None and upstream_group not in key_groups:
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 '{upstream_group}'（模型 {model}）",
            )

    # ------------------------------------------------------------
    # 转发 + 重试
    # ------------------------------------------------------------

    async def _forward(self, candidates: list[dict], body: dict, is_stream: bool,
                       max_attempts: int, response_timeout: float,
                       first_chunk_timeout: float) -> JSONResponse | StreamingResponse:
        """按候选顺序转发，失败自动换下一个"""
        tried = []
        for i in range(max_attempts):
            cand = candidates[i]
            model = cand["model"]
            upstream_id = cand.get("upstream", self.config.default_upstream)
            model_max_output = cand.get("max_output")
            tried.append(model)

            if i > 0 and self.config.log_routing:
                log.info(f"重试({i+1}/{max_attempts}): "
                         f"{candidates[i-1]['model'].split('/')[-1]} 失败 → 尝试 {model.split('/')[-1]}")

            fmt = self.config.get_model_protocol(upstream_id, model)

            if fmt == "anthropic":
                result = await (try_stream_anthropic if is_stream else try_non_stream_anthropic)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                )
            elif fmt == "responses":
                result = await (try_stream_responses if is_stream else try_non_stream_responses)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                )
            else:
                result = await (try_stream if is_stream else try_non_stream)(
                    model, upstream_id, body, {},
                    first_chunk_timeout if is_stream else response_timeout,
                    self.http_client, self.config, self.health, model_max_output,
                )

            if result is not None:
                if i > 0 and self.config.log_routing:
                    log.info(f"重试成功: {candidates[i-1]['model'].split('/')[-1]} → {model.split('/')[-1]}")
                return result

        raise HTTPException(
            status_code=503,
            detail=f"所有模型均不可用 (尝试了: {', '.join(m.split('/')[-1] for m in tried)})",
        )

    # ------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------

    async def chat_completions(self, body: dict, key_groups: set[str] | None):
        """POST /v1/chat/completions 主处理"""
        original_model = body.get("model", "")
        is_stream = body.get("stream", False)

        candidates, _ = self._resolve_candidates(original_model, body, key_groups)
        if not candidates:
            raise HTTPException(status_code=503, detail="无可用模型")

        retry_cfg = self.config.retry_config
        max_attempts = min(retry_cfg.get("max_attempts", 3), len(candidates))
        response_timeout = retry_cfg.get("response_timeout", 12)
        first_chunk_timeout = retry_cfg.get("first_chunk_timeout", 6)

        return await self._forward(
            candidates, body, is_stream, max_attempts, response_timeout, first_chunk_timeout
        )

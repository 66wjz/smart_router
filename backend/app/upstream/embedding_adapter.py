"""
OpenAI 兼容向量（Embeddings）转发适配器 - CH-054

与聊天适配器的差异：
- 非流式、无 SSE、无 messages/max_tokens 语义
- 请求体除 model 外原样透传（input / encoding_format / dimensions 等）
- 复用 Key 池轮询、智能重试、CH-040 错误包识别、CH-050 响应头安全化
"""

import asyncio
import copy
import json
import logging
import time

import httpx
from fastapi.responses import JSONResponse

from app.core.config import AppConfig
from app.core.health import ModelHealth
from app.upstream.openai_adapter import (
    _RetryLoop,
    _build_endpoint,
    _capture_forward,
    _capture_response,
    _elapsed_ms,
    _extract_error_detail,
    _extract_wrapped_error,
    _note_attempt,
)

log = logging.getLogger("router")

# 嵌入服务冷启动可能较慢，默认 60s（高于聊天的 12s）
DEFAULT_EMBEDDING_TIMEOUT = 60.0


def embedding_timeout(app_config: AppConfig) -> float:
    """嵌入请求超时（秒）：sys_setting.embedding_timeout_seconds > 默认 60s"""
    try:
        value = app_config._settings.get("embedding_timeout_seconds", DEFAULT_EMBEDDING_TIMEOUT)
        return float(value or DEFAULT_EMBEDDING_TIMEOUT)
    except Exception:
        return DEFAULT_EMBEDDING_TIMEOUT


def _clean_body(body: dict, model: str) -> dict:
    """复制请求体并替换模型名；移除聊天专属字段（stream / stream_options）"""
    modified = copy.deepcopy(body)
    modified["model"] = model
    modified.pop("stream", None)
    modified.pop("stream_options", None)
    return modified


async def _post_embedding(
    model: str,
    upstream_id: str,
    body: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
) -> tuple[dict | None, str | None, dict]:
    """向单个上游发起嵌入请求，返回 (响应 JSON, 错误摘要, 响应头)

    Key 池循环与聊天一致：401/403/429/超时/连接异常换 Key；
    智能重试开启时 5xx 也重试；200 + 错误包按失败处理。
    """
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    if not base_url:
        return None, "上游未配置 Base URL", {}
    if not keys:
        return None, "上游未配置可用 API Key", {}

    modified = _clean_body(body, model)
    url = _build_endpoint(base_url, "/v1/embeddings")
    if not url:
        return None, "上游 Base URL 无效", {}

    _capture_forward(modified)

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    last_error = "上游所有 Key 均失败"

    for _ in range(rl.budget):
        t_attempt = time.time()
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=modified, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except (asyncio.TimeoutError, httpx.TimeoutException):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            last_error = f"连接超时（{timeout_sec}s）"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), last_error)
            log.warning(f"嵌入 [{upstream_id}] Key 连接超时 ({timeout_sec}s)，换下一个 Key")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            last_error = f"连接异常: {e}"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), last_error)
            log.warning(f"嵌入 [{upstream_id}] Key 连接异常: {e}，换下一个 Key")
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            last_error = f"响应超时（{timeout_sec}s）"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), last_error)
            log.warning(f"嵌入 [{upstream_id}] Key 响应超时 ({timeout_sec}s)，换下一个 Key")
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            last_error = f"响应异常: {e}"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), last_error)
            continue

        if resp.status_code == 200:
            await resp.aclose()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            wrapped_error = _extract_wrapped_error(parsed)
            if wrapped_error:
                app_config.key_pool.record_fail(upstream_id, api_key)
                rl.on_failure(api_key)
                last_error = wrapped_error
                rl.log_retry(f"响应体错误包: {wrapped_error[:80]}")
                _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt), wrapped_error)
                _capture_response(raw)
                health.record_fail(upstream_id, model)
                continue
            app_config.key_pool.record_success(upstream_id, api_key)
            health.record_success(upstream_id, model)
            _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt))
            _capture_response(raw)
            return parsed, None, rl.response_headers()

        await resp.aclose()
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            last_error = f"Key 返回 HTTP {resp.status_code}"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                          "Key 鉴权/限流失败，换 Key")
            log.warning(f"嵌入 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
            continue
        if rl.retriable_status(resp.status_code):
            rl.on_failure(api_key)
            last_error = f"HTTP {resp.status_code}"
            rl.log_retry(last_error)
            _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                          "可重试状态码")
            continue
        health.record_fail(upstream_id, model)
        last_error = _extract_error_detail(raw, resp.status_code)
        log.warning(f"嵌入模型 {model.split('/')[-1]} 返回错误: HTTP {resp.status_code} {last_error}")
        _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt), last_error)
        _capture_response(raw)
        return None, last_error, rl.response_headers()

    return None, last_error, rl.response_headers()


async def try_non_stream_embedding(
    model: str,
    upstream_id: str,
    body: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
) -> JSONResponse | None:
    """尝试一次嵌入请求：成功返回原样 JSONResponse，失败返回 None"""
    parsed, _error, headers = await _post_embedding(
        model, upstream_id, body, timeout_sec, http_client, app_config, health,
    )
    if parsed is None:
        return None
    return JSONResponse(status_code=200, content=parsed, headers=headers)


async def test_non_stream_embedding(
    model: str,
    upstream_id: str,
    text: str,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
) -> tuple[str | None, str | None, int | None]:
    """管理端单模型测试：返回 (结果摘要, 错误信息, 向量维度)"""
    body = {"model": model, "input": text or "测试文本"}
    parsed, error, _headers = await _post_embedding(
        model, upstream_id, body, timeout_sec, http_client, app_config, health,
    )
    if parsed is None:
        return None, error or "嵌入测试失败", None

    data = parsed.get("data") or []
    dimension = None
    try:
        if data and isinstance(data[0], dict):
            embedding = data[0].get("embedding") or []
            dimension = len(embedding) if isinstance(embedding, list) else None
    except Exception:
        dimension = None
    summary = f"返回 {len(data)} 条向量" + (f"，维度 {dimension}" if dimension else "")
    return summary, None, dimension


__all__ = ["embedding_timeout", "try_non_stream_embedding", "test_non_stream_embedding"]

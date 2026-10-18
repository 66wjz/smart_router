"""
OpenAI Responses 格式出站适配器（CH-014）
实现 OpenAI chat/completions 格式 ↔ Responses API 格式的转换与转发：
- 请求：openai chat（messages）→ Responses（input/instructions）
- 响应：Responses（output 数组）→ openai chat（choices）
- 流式：Responses SSE 事件 → openai SSE chunk
复用 Key 池 + _RetryLoop（智能重试）+ 首字节分界线（与 openai/anthropic 适配器同骨架）
"""

import asyncio
import copy
import json
import logging
import time

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import AppConfig
from app.core.health import ModelHealth
from app.upstream.openai_adapter import _build_endpoint, _RetryLoop

log = logging.getLogger("router")


# CH-026：转换函数已拆到 responses_convert.py，此处重新导出以保持既有 import 路径不变
from app.upstream.responses_convert import (  # noqa: E402,F401
    OpenaiToResponsesSSE,
    _convert_sse_line,
    _extract_text,
    convert_request_openai_to_responses,
    convert_request_responses_to_openai,
    convert_response_openai_to_responses,
    convert_response_responses_to_openai,
    convert_responses_sse_data_to_openai,
)


# ============================================================
# 请求转发（Responses 上游）
# ============================================================

async def try_non_stream_responses(
    model: str,
    upstream_id: str,
    body: dict,
    request_headers: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
    max_output: int | None = None,
) -> JSONResponse | None:
    """尝试非流式请求到 Responses 格式上游（Key 池 + 智能重试，与 openai 适配器同骨架）"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    if not base_url or not keys:
        health.record_fail(upstream_id, model)
        return None

    modified = copy.deepcopy(body)
    modified["model"] = model
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    responses_body = convert_request_openai_to_responses(modified)
    url = _build_endpoint(base_url, "/v1/responses")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=responses_body, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except (asyncio.TimeoutError, httpx.TimeoutException):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 连接超时 ({timeout_sec}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 连接超时 ({timeout_sec}s)，换下一个 Key")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 连接异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 连接异常: {e}，换下一个 Key")
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 响应超时 ({timeout_sec}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 响应超时 ({timeout_sec}s)，换下一个 Key")
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 响应异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 响应异常: {e}，换下一个 Key")
            continue

        if resp.status_code == 200:
            await resp.aclose()
            app_config.key_pool.record_success(upstream_id, api_key)
            health.record_success(upstream_id, model)
            openai_resp = convert_response_responses_to_openai(json.loads(raw), model)
            return JSONResponse(status_code=200, content=openai_resp, headers=rl.response_headers())
        await resp.aclose()
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 返回 HTTP {resp.status_code}")
            log.warning(f"Key 池 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
            continue
        if rl.retriable_status(resp.status_code):
            rl.on_failure(api_key)
            rl.log_retry(f"HTTP {resp.status_code}")
            continue
        health.record_fail(upstream_id, model)
        log.warning(f"模型 {model.split('/')[-1]} (Responses) 返回错误: HTTP {resp.status_code}")
        return None
    return None


async def try_stream_responses(
    model: str,
    upstream_id: str,
    body: dict,
    request_headers: dict,
    first_chunk_timeout: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
    max_output: int | None = None,
    *,
    response_timeout: float | None = None,
) -> StreamingResponse | None:
    """尝试流式请求到 Responses 格式上游，SSE 事件转 openai 格式（首字节分界线不变）

    response_timeout: 等待上游返回「响应头」的超时（秒）。None = 不限（保持旧行为）。"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    keys = app_config.get_upstream_keys(upstream_id)
    if not base_url or not keys:
        health.record_fail(upstream_id, model)
        return None

    modified = copy.deepcopy(body)
    modified["model"] = model
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    responses_body = convert_request_openai_to_responses(modified)
    responses_body["stream"] = True
    url = _build_endpoint(base_url, "/v1/responses")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            send_coro = http_client.send(
                http_client.build_request("POST", url, json=responses_body, headers=headers),
                stream=True,
            )
            # 等响应头：有配置就走 wait_for，未配置保持旧行为（受 httpx 全局超时管）
            resp = (await asyncio.wait_for(send_coro, timeout=response_timeout)
                    if response_timeout else await send_coro)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"流式响应头超时 ({response_timeout}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 流式响应头超时 ({response_timeout}s)，换下一个 Key")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 流式连接异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 流式连接异常: {e}，换下一个 Key")
            continue

        if resp.status_code != 200:
            await resp.aread()
            await resp.aclose()
            if resp.status_code in (401, 403, 429):
                app_config.key_pool.record_fail(upstream_id, api_key)
                rl.on_failure(api_key)
                rl.log_retry(f"Key 返回 HTTP {resp.status_code}")
                log.warning(f"Key 池 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
                continue
            if rl.retriable_status(resp.status_code):
                rl.on_failure(api_key)
                rl.log_retry(f"流式 HTTP {resp.status_code}（首字节前）")
                continue
            health.record_fail(upstream_id, model)
            log.warning(f"模型 {model.split('/')[-1]} (Responses) 流式返回错误: HTTP {resp.status_code}")
            return None

        line_iter = resp.aiter_lines()
        try:
            first_line = await asyncio.wait_for(
                line_iter.__anext__(), timeout=first_chunk_timeout
            )
        except StopAsyncIteration:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry("流式空响应")
            log.warning(f"Key 池 [{upstream_id}] Key 流式空响应，换下一个 Key")
            continue
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"首包超时 ({first_chunk_timeout}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 首包超时 ({first_chunk_timeout}s)，换下一个 Key")
            continue

        app_config.key_pool.record_success(upstream_id, api_key)
        health.record_success(upstream_id, model)
        first_chunk = _convert_sse_line(first_line, model)

        async def generate():
            try:
                if first_chunk:
                    yield first_chunk
                async for line in line_iter:
                    converted = _convert_sse_line(line, model)
                    if converted:
                        yield converted
                yield "data: [DONE]\n\n"
            except Exception as e:
                log.error(f"Responses 流式传输中断: {model.split('/')[-1]} {e}")
                health.record_fail(upstream_id, model)
            finally:
                try:
                    await resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream", headers=rl.response_headers())
    return None


# ============================================================
# 管理端模型测试
# ============================================================

async def test_non_stream_responses(
    model: str,
    upstream_id: str,
    body: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
) -> tuple[str | None, str | None]:
    """管理端单模型测试（Responses 格式上游）：返回 (回复文本, 错误信息)"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    url = _build_endpoint(base_url, "/v1/responses")
    if not url:
        return None, "上游未配置 Base URL"
    if not keys:
        return None, "上游未配置可用 API Key"

    modified = copy.deepcopy(body)
    modified["model"] = model
    responses_body = convert_request_openai_to_responses(modified)

    last_error = "上游所有 Key 均失败"
    for _ in range(len(keys)):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=responses_body, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接超时（{timeout_sec}s）"
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接异常: {e}"
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应超时（{timeout_sec}s）"
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应读取异常: {e}"
            continue

        if resp.status_code == 200:
            await resp.aclose()
            app_config.key_pool.record_success(upstream_id, api_key)
            try:
                data = json.loads(raw)
                parts = [
                    str(c.get("text", ""))
                    for item in data.get("output") or []
                    if item.get("type") == "message"
                    for c in item.get("content") or []
                    if c.get("type") == "output_text"
                ]
                content = "".join(parts)
            except Exception:
                content = None
            return content or "（无文本回复）", None
        await resp.aclose()
        from app.upstream.openai_adapter import _extract_error_detail
        detail = _extract_error_detail(raw, resp.status_code)
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"HTTP {resp.status_code} {detail}（已换 Key 重试）"
            continue
        return None, f"HTTP {resp.status_code} {detail}".strip()
    return None, last_error

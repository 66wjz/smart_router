"""
Anthropic 格式适配器
实现 OpenAI 格式 ↔ Anthropic 格式的双向转换：
- 请求：OpenAI chat/completions 格式 → Anthropic /v1/messages 格式
- 响应：Anthropic 响应 → OpenAI 响应格式
- 流式：Anthropic SSE 事件 → OpenAI SSE 格式
从 v4 upstream/anthropic_adapter.py 迁移，import 路径改为 app 包结构
"""

import asyncio
import copy
import json
import logging
import time
import uuid
from typing import Any

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import AppConfig
from app.core.health import ModelHealth
from app.upstream.openai_adapter import _RetryLoop

log = logging.getLogger("router")


def _build_endpoint(base_url: str, path: str) -> str:
    """拼接请求端点，容错 base_url 误填完整 URL（已含目标路径时直接使用）"""
    base = (base_url or "").rstrip("/")
    if not base:
        return ""
    if base.endswith(path):
        return base
    return f"{base}{path}"


# CH-026：转换函数已拆到 anthropic_convert.py，此处重新导出以保持既有 import 路径不变
from app.upstream.anthropic_convert import (  # noqa: E402,F401
    ANTHROPIC_VERSION,
    OpenaiToAnthropicSSE,
    _anthropic_content_to_openai,
    _anthropic_image_block_to_openai,
    _convert_content_to_anthropic,
    _convert_tool_choice_to_anthropic,
    _convert_tools_to_anthropic,
    _make_sse_chunk,
    convert_anthropic_sse_line_to_openai,
    convert_request_anthropic_to_openai,
    convert_request_openai_to_anthropic,
    convert_response_anthropic_to_openai,
    convert_response_openai_to_anthropic,
)


# ============================================================
# 请求转发（Anthropic 上游）
# ============================================================

async def try_non_stream_anthropic(
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
    """尝试非流式请求到 Anthropic 格式上游
    Key 池循环：401/403/429/连接超时/响应超时视为该 Key 失败，换下一个 Key 重试
    使用 send(stream=True)+aread()+显式 aclose，避免超时取消产生脏连接阻塞后续请求"""
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

    anthropic_body = convert_request_openai_to_anthropic(modified)
    url = _build_endpoint(base_url, "/v1/messages")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=anthropic_body, headers=headers),
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
            openai_resp = convert_response_anthropic_to_openai(json.loads(raw), model)
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
        log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 返回错误: HTTP {resp.status_code}")
        return None
    return None


async def try_stream_anthropic(
    model: str,
    upstream_id: str,
    body: dict,
    request_headers: dict,
    first_chunk_timeout: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
    max_output: int | None = None,
) -> StreamingResponse | None:
    """尝试流式请求到 Anthropic 格式上游，自动转换 SSE 格式
    Key 池循环：401/403/429/首包超时/空响应/连接异常视为该 Key 失败，换下一个 Key 重试"""
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

    anthropic_body = convert_request_openai_to_anthropic(modified)
    anthropic_body["stream"] = True
    url = _build_endpoint(base_url, "/v1/messages")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        try:
            resp = await http_client.send(
                http_client.build_request("POST", url, json=anthropic_body, headers=headers),
                stream=True,
            )
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
            log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 流式返回错误: HTTP {resp.status_code}")
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
        first_chunk = convert_anthropic_sse_line_to_openai(first_line, model)

        async def generate():
            try:
                if first_chunk:
                    yield first_chunk
                async for line in line_iter:
                    if not line:
                        continue
                    converted = convert_anthropic_sse_line_to_openai(line, model)
                    if converted:
                        yield converted
            except Exception as e:
                log.error(f"Anthropic 流式传输中断: {model.split('/')[-1]} {e}")
                health.record_fail(upstream_id, model)
            finally:
                try:
                    await resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream", headers=rl.response_headers())
    return None


async def test_non_stream_anthropic(
    model: str,
    upstream_id: str,
    body: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
) -> tuple[str | None, str | None]:
    """管理端单模型测试（Anthropic 格式上游）：返回 (回复文本, 错误信息)
    错误信息具体到 HTTP 状态码+响应体 / 连接超时 / 响应超时 / 连接异常；全部 Key 失败时返回最后一次错误"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    url = _build_endpoint(base_url, "/v1/messages")
    if not url:
        return None, "上游未配置 Base URL"
    if not keys:
        return None, "上游未配置可用 API Key"

    modified = copy.deepcopy(body)
    modified["model"] = model
    anthropic_body = convert_request_openai_to_anthropic(modified)

    last_error = "上游所有 Key 均失败"
    for _ in range(len(keys)):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=anthropic_body, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接超时（{timeout_sec}s）"
            log.warning(f"测试 [{upstream_id}] Key 连接超时，换下一个 Key")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接异常: {e}"
            log.warning(f"测试 [{upstream_id}] Key 连接异常: {e}，换下一个 Key")
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应超时（{timeout_sec}s）"
            log.warning(f"测试 [{upstream_id}] Key 响应超时，换下一个 Key")
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应读取异常: {e}"
            log.warning(f"测试 [{upstream_id}] Key 响应异常: {e}，换下一个 Key")
            continue

        if resp.status_code == 200:
            await resp.aclose()
            app_config.key_pool.record_success(upstream_id, api_key)
            try:
                anthropic_resp = json.loads(raw)
                content = "".join(
                    b.get("text", "") for b in anthropic_resp.get("content", []) if b.get("type") == "text"
                )
            except Exception:
                content = None
            return content or "（无文本回复）", None
        await resp.aclose()
        detail = _extract_anthropic_error(raw)
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"HTTP {resp.status_code} {detail}（已换 Key 重试）"
            log.warning(f"测试 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
            continue
        return None, f"HTTP {resp.status_code} {detail}".strip()
    return None, last_error


def _extract_anthropic_error(raw: bytes) -> str:
    """从 Anthropic 非 200 响应体中提取具体错误信息"""
    text = ""
    try:
        parsed = json.loads(raw)
        err = parsed.get("error")
        if isinstance(err, dict):
            text = err.get("message") or err.get("type") or json.dumps(err, ensure_ascii=False)
        else:
            text = json.dumps(parsed, ensure_ascii=False)[:300]
    except Exception:
        text = raw.decode("utf-8", "ignore")[:300]
    return (text or "").strip()

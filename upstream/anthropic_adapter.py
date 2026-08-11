"""
Anthropic 格式适配器
实现 OpenAI 格式 ↔ Anthropic 格式的双向转换：
- 请求：OpenAI chat/completions 格式 → Anthropic /v1/messages 格式
- 响应：Anthropic 响应 → OpenAI 响应格式
- 流式：Anthropic SSE 事件 → OpenAI SSE 格式

Anthropic API 文档: https://docs.anthropic.com/en/api/messages
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

from core.config import AppConfig
from core.health import ModelHealth

log = logging.getLogger("router")

ANTHROPIC_VERSION = "2023-06-01"


# ============================================================
# 请求转换: OpenAI → Anthropic
# ============================================================

def convert_request_openai_to_anthropic(body: dict) -> dict:
    """
    将 OpenAI chat/completions 请求体转换为 Anthropic /v1/messages 请求体。
    """
    messages = body.get("messages", [])
    system_prompt = None
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # system 消息单独提取
        if role == "system":
            system_prompt = content if isinstance(content, str) else _convert_content_to_anthropic(content)
            continue

        # 转换 content
        if isinstance(content, str):
            anthropic_content = content
        elif isinstance(content, list):
            anthropic_content = _convert_content_to_anthropic(content)
        else:
            anthropic_content = str(content)

        anthropic_messages.append({
            "role": role,
            "content": anthropic_content,
        })

    result: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": anthropic_messages,
        "max_tokens": body.get("max_tokens", 4096),
    }

    if system_prompt:
        result["system"] = system_prompt

    # stream
    if body.get("stream"):
        result["stream"] = True

    # temperature
    if "temperature" in body:
        result["temperature"] = body["temperature"]

    # top_p
    if "top_p" in body:
        result["top_p"] = body["top_p"]

    # stop_sequences (OpenAI 的 stop → Anthropic 的 stop_sequences)
    if "stop" in body:
        stop = body["stop"]
        if isinstance(stop, str):
            result["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            result["stop_sequences"] = stop

    # tools 转换
    if body.get("tools"):
        result["tools"] = _convert_tools_to_anthropic(body["tools"])
        if body.get("tool_choice"):
            result["tool_choice"] = _convert_tool_choice_to_anthropic(body["tool_choice"])

    return result


def _convert_content_to_anthropic(content: list) -> list:
    """转换 OpenAI 多模态 content 到 Anthropic 格式"""
    result = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type", "")

        if ptype == "text":
            result.append({"type": "text", "text": part.get("text", "")})

        elif ptype == "image_url":
            url = part.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                # base64 格式: data:image/png;base64,xxxx
                try:
                    media_type, base64_data = url.split(";base64,", 1)
                    media_type = media_type.replace("data:", "")
                    result.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data,
                        },
                    })
                except ValueError:
                    result.append({"type": "text", "text": f"[image: {url[:50]}...]"})
            else:
                # URL 格式
                result.append({
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": url,
                    },
                })

    return result


def _convert_tools_to_anthropic(tools: list) -> list:
    """转换 OpenAI tools 到 Anthropic tools 格式"""
    result = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            result.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
    return result


def _convert_tool_choice_to_anthropic(tool_choice: Any) -> dict:
    """转换 OpenAI tool_choice 到 Anthropic 格式"""
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"type": "auto"}
        elif tool_choice == "none":
            return {"type": "none"}
        elif tool_choice == "required":
            return {"type": "any"}
    elif isinstance(tool_choice, dict):
        func = tool_choice.get("function", {})
        return {"type": "tool", "name": func.get("name", "")}
    return {"type": "auto"}


# ============================================================
# 响应转换: Anthropic → OpenAI
# ============================================================

def convert_response_anthropic_to_openai(anthropic_resp: dict, model: str) -> dict:
    """将 Anthropic /v1/messages 响应转换为 OpenAI chat/completions 格式"""
    content = anthropic_resp.get("content", [])
    text_parts = []
    tool_calls = []

    for i, block in enumerate(content):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
                "index": i,
            })

    # 组装 message
    message = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    # usage
    usage_in = anthropic_resp.get("usage", {})
    usage = {
        "prompt_tokens": usage_in.get("input_tokens", 0),
        "completion_tokens": usage_in.get("output_tokens", 0),
        "total_tokens": usage_in.get("input_tokens", 0) + usage_in.get("output_tokens", 0),
    }

    # stop_reason 转换
    stop_reason = anthropic_resp.get("stop_reason", "")
    finish_reason = {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "tool_use": "tool_calls",
    }.get(stop_reason, "stop")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }],
        "usage": usage,
    }


# ============================================================
# 流式转换: Anthropic SSE → OpenAI SSE
# ============================================================

def convert_anthropic_sse_line_to_openai(line: str, model: str) -> str | None:
    """
    将 Anthropic SSE 事件转换为 OpenAI SSE 格式。
    返回转换后的 SSE data 行，或 None（跳过该事件）。
    """
    if not line.startswith("data: "):
        return None

    data_str = line[6:].strip()
    if data_str == "[DONE]":
        return "data: [DONE]\n\n"

    try:
        event = json.loads(data_str)
    except json.JSONDecodeError:
        return None

    event_type = event.get("type", "")

    # message_start → 生成初始 chunk
    if event_type == "message_start":
        msg = event.get("message", {})
        return _make_sse_chunk(model, {"role": "assistant", "content": ""}, None)

    # content_block_start → 可能是 tool_use 开始
    if event_type == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            tool_call = {
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {"name": block.get("name", ""), "arguments": ""},
                "index": event.get("index", 0),
            }
            delta = {"tool_calls": [tool_call]}
            return _make_sse_chunk(model, delta, None)
        elif block.get("type") == "text":
            text = block.get("text", "")
            if text:
                return _make_sse_chunk(model, {"content": text}, None)
        return None

    # content_block_delta → 文本增量或 tool 参数增量
    if event_type == "content_block_delta":
        delta_info = event.get("delta", {})
        if delta_info.get("type") == "text_delta":
            text = delta_info.get("text", "")
            if text:
                return _make_sse_chunk(model, {"content": text}, None)
        elif delta_info.get("type") == "input_json_delta":
            partial_json = delta_info.get("partial_json", "")
            idx = event.get("index", 0)
            tool_call = {
                "index": idx,
                "function": {"arguments": partial_json},
            }
            return _make_sse_chunk(model, {"tool_calls": [tool_call]}, None)
        return None

    # message_delta → stop reason
    if event_type == "message_delta":
        delta = event.get("delta", {})
        stop_reason = delta.get("stop_reason", "")
        finish_reason = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }.get(stop_reason, "stop")
        return _make_sse_chunk(model, {}, finish_reason)

    # 其他事件类型跳过
    return None


def _make_sse_chunk(model: str, delta: dict, finish_reason: str | None) -> str:
    """构造 OpenAI 格式的 SSE chunk"""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


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
    """尝试非流式请求到 Anthropic 格式上游"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    api_key = upstream.get("api_key", "")

    modified = copy.deepcopy(body)
    modified["model"] = model

    # max_tokens 调整
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    # 转换为 Anthropic 请求格式
    anthropic_body = convert_request_openai_to_anthropic(modified)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    url = f"{base_url}/v1/messages"

    try:
        resp = await asyncio.wait_for(
            http_client.post(url, json=anthropic_body, headers=headers),
            timeout=timeout_sec,
        )
        if resp.status_code == 200:
            health.record_success(model)
            openai_resp = convert_response_anthropic_to_openai(resp.json(), model)
            return JSONResponse(status_code=200, content=openai_resp)
        else:
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 返回错误: HTTP {resp.status_code}")
            return None
    except (asyncio.TimeoutError, httpx.TimeoutException):
        health.record_fail(model)
        log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 响应超时 ({timeout_sec}s)")
        return None
    except Exception as e:
        health.record_fail(model)
        log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 请求异常: {e}")
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
    """尝试流式请求到 Anthropic 格式上游，自动转换 SSE 格式"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    api_key = upstream.get("api_key", "")

    modified = copy.deepcopy(body)
    modified["model"] = model

    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    # 转换为 Anthropic 请求格式（启用 stream）
    anthropic_body = convert_request_openai_to_anthropic(modified)
    anthropic_body["stream"] = True

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    url = f"{base_url}/v1/messages"

    try:
        resp = await http_client.send(
            http_client.build_request("POST", url, json=anthropic_body, headers=headers),
            stream=True,
        )

        if resp.status_code != 200:
            error_text = await resp.aread()
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 流式返回错误: HTTP {resp.status_code}")
            return None

        # 等待首包
        line_iter = resp.aiter_lines()
        try:
            first_line = await asyncio.wait_for(
                line_iter.__anext__(), timeout=first_chunk_timeout
            )
        except StopAsyncIteration:
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 流式空响应")
            return None
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 首包超时 ({first_chunk_timeout}s)")
            return None

        health.record_success(model)

        # 缓存首包转换结果
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
                health.record_fail(model)
            finally:
                try:
                    await resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        log.warning(f"模型 {model.split('/')[-1]} (Anthropic) 流式连接异常: {e}")
        health.record_fail(model)
        return None

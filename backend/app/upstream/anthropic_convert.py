"""
Anthropic ↔ OpenAI 转换 · 出站段（CH-026）

把 OpenAI 请求转成 Anthropic 请求、把 Anthropic 响应/SSE 转回 OpenAI 格式。
入站逆转换见 anthropic_convert_in.py。
"""

import json
import logging
import time
import uuid
from typing import Any

log = logging.getLogger("router")

ANTHROPIC_VERSION = "2023-06-01"

# ============================================================
# 请求转换: OpenAI → Anthropic
# ============================================================

def convert_request_openai_to_anthropic(body: dict) -> dict:
    """将 OpenAI chat/completions 请求体转换为 Anthropic /v1/messages 请求体。"""
    messages = body.get("messages", [])
    system_prompt = None
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            system_prompt = content if isinstance(content, str) else _convert_content_to_anthropic(content)
            continue

        if isinstance(content, str):
            anthropic_content = content
        elif isinstance(content, list):
            anthropic_content = _convert_content_to_anthropic(content)
        else:
            anthropic_content = str(content)

        anthropic_messages.append({"role": role, "content": anthropic_content})

    result: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": anthropic_messages,
        "max_tokens": body.get("max_tokens", 4096),
    }

    if system_prompt:
        result["system"] = system_prompt
    if body.get("stream"):
        result["stream"] = True
    if "temperature" in body:
        result["temperature"] = body["temperature"]
    if "top_p" in body:
        result["top_p"] = body["top_p"]
    if "stop" in body:
        stop = body["stop"]
        if isinstance(stop, str):
            result["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            result["stop_sequences"] = stop
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
                try:
                    media_type, base64_data = url.split(";base64,", 1)
                    media_type = media_type.replace("data:", "")
                    result.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": base64_data},
                    })
                except ValueError:
                    result.append({"type": "text", "text": f"[image: {url[:50]}...]"})
            else:
                result.append({
                    "type": "image",
                    "source": {"type": "url", "url": url},
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

    message = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    usage_in = anthropic_resp.get("usage", {})
    usage = {
        "prompt_tokens": usage_in.get("input_tokens", 0),
        "completion_tokens": usage_in.get("output_tokens", 0),
        "total_tokens": usage_in.get("input_tokens", 0) + usage_in.get("output_tokens", 0),
    }

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
    """将 Anthropic SSE 事件转换为 OpenAI SSE 格式。"""
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

    if event_type == "message_start":
        return _make_sse_chunk(model, {"role": "assistant", "content": ""}, None)

    if event_type == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            tool_call = {
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {"name": block.get("name", ""), "arguments": ""},
                "index": event.get("index", 0),
            }
            return _make_sse_chunk(model, {"tool_calls": [tool_call]}, None)
        elif block.get("type") == "text":
            text = block.get("text", "")
            if text:
                return _make_sse_chunk(model, {"content": text}, None)
        return None

    if event_type == "content_block_delta":
        delta_info = event.get("delta", {})
        if delta_info.get("type") == "text_delta":
            text = delta_info.get("text", "")
            if text:
                return _make_sse_chunk(model, {"content": text}, None)
        elif delta_info.get("type") == "input_json_delta":
            partial_json = delta_info.get("partial_json", "")
            idx = event.get("index", 0)
            return _make_sse_chunk(model, {"tool_calls": [{"index": idx, "function": {"arguments": partial_json}}]}, None)
        return None

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

    return None


def _make_sse_chunk(model: str, delta: dict, finish_reason: str | None) -> str:
    """构造 OpenAI 格式的 SSE chunk"""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


# CH-026：入站逆转换已拆到 anthropic_convert_in.py，此处重新导出保持既有 import 路径不变
from app.upstream.anthropic_convert_in import (  # noqa: E402,F401
    OpenaiToAnthropicSSE,
    _anthropic_content_to_openai,
    _anthropic_image_block_to_openai,
    convert_request_anthropic_to_openai,
    convert_response_openai_to_anthropic,
)

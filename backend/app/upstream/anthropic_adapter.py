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

ANTHROPIC_VERSION = "2023-06-01"


def _build_endpoint(base_url: str, path: str) -> str:
    """拼接请求端点，容错 base_url 误填完整 URL（已含目标路径时直接使用）"""
    base = (base_url or "").rstrip("/")
    if not base:
        return ""
    if base.endswith(path):
        return base
    return f"{base}{path}"


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


# ============================================================
# 入站逆转换（CH-009）：Anthropic → OpenAI
# ============================================================

def _anthropic_content_to_openai(content) -> tuple[str, list[dict], list[dict]]:
    """解析 anthropic message content → (文本, tool_calls, tool_results)"""
    if isinstance(content, str):
        return content, [], []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {"name": block.get("name", ""), "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)},
            })
        elif btype == "tool_result":
            inner = block.get("content", "")
            if isinstance(inner, list):
                inner = "".join(str(b.get("text", "")) for b in inner if isinstance(b, dict) and b.get("type") == "text")
            tool_results.append({"tool_call_id": block.get("tool_use_id", ""), "content": str(inner)})
    return "".join(text_parts), tool_calls, tool_results


def convert_request_anthropic_to_openai(body: dict) -> dict:
    """将 Anthropic /v1/messages 请求体转换为 OpenAI chat/completions 请求体（入站）"""
    messages: list[dict] = []

    system = body.get("system")
    if system:
        if isinstance(system, list):
            system = "".join(str(b.get("text", "")) for b in system if isinstance(b, dict) and b.get("type") == "text")
        messages.append({"role": "system", "content": str(system)})

    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        text, tool_calls, tool_results = _anthropic_content_to_openai(msg.get("content"))
        if tool_results:
            for tr in tool_results:
                messages.append({"role": "tool", "tool_call_id": tr["tool_call_id"], "content": tr["content"]})
        entry: dict = {"role": role, "content": text}
        if tool_calls:
            entry["tool_calls"] = tool_calls
        if text or tool_calls:
            messages.append(entry)

    result: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": messages,
    }
    if body.get("max_tokens") is not None:
        result["max_tokens"] = body["max_tokens"]
    if body.get("stream"):
        result["stream"] = True
    if "temperature" in body:
        result["temperature"] = body["temperature"]
    if "top_p" in body:
        result["top_p"] = body["top_p"]
    if body.get("stop_sequences"):
        result["stop"] = body["stop_sequences"]
    if body.get("tools"):
        result["tools"] = [
            {"type": "function", "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            }}
            for t in body["tools"] if t.get("name")
        ]
    return result


def convert_response_openai_to_anthropic(openai_resp: dict, model: str) -> dict:
    """将 OpenAI chat/completions 响应转换为 Anthropic /v1/messages 响应（入站）"""
    choice = (openai_resp.get("choices") or [{}])[0]
    message = choice.get("message", {})
    content: list[dict] = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {"raw": fn.get("arguments", "")}
        content.append({"type": "tool_use", "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                        "name": fn.get("name", ""), "input": args})

    stop_reason = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "refusal",
    }.get(choice.get("finish_reason") or "stop", "end_turn")

    usage_in = openai_resp.get("usage") or {}
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": usage_in.get("prompt_tokens", 0),
            "output_tokens": usage_in.get("completion_tokens", 0),
        },
    }


class OpenaiToAnthropicSSE:
    """openai SSE chunk → anthropic SSE 事件序列（入站流式状态机，CH-009）"""

    def __init__(self, model: str):
        self.model = model
        self.started = False
        self.block_open = False
        self.block_index = 0
        self.tool_block = False
        self.closed = False

    @staticmethod
    def _ev(etype: str, payload: dict) -> str:
        return f"event: {etype}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def feed(self, chunk_str: str) -> list[str]:
        out: list[str] = []
        if self.closed:
            return out
        line = chunk_str.strip()
        if not line.startswith("data:"):
            return out
        payload = line[5:].strip()
        if payload == "[DONE]":
            out.extend(self.close())
            return out
        try:
            data = json.loads(payload)
        except Exception:
            return out
        if "error" in data:
            out.append(self._ev("error", {"type": "error", "error": {"type": "api_error", "message": str(data["error"])}}))
            out.extend(self.close())
            return out

        choice = (data.get("choices") or [{}])[0]
        delta = choice.get("delta", {})
        finish = choice.get("finish_reason")

        if not self.started:
            self.started = True
            out.append(self._ev("message_start", {
                "type": "message_start",
                "message": {"id": f"msg_{uuid.uuid4().hex[:24]}", "type": "message", "role": "assistant",
                            "model": self.model, "content": [], "stop_reason": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0}},
            }))

        if delta.get("content"):
            if self.block_open and self.tool_block:
                out.append(self._ev("content_block_stop", {"type": "content_block_stop", "index": self.block_index}))
                self.block_open = False
                self.block_index += 1
            if not self.block_open:
                out.append(self._ev("content_block_start", {"type": "content_block_start", "index": self.block_index,
                                                            "content_block": {"type": "text", "text": ""}}))
                self.block_open = True
                self.tool_block = False
            out.append(self._ev("content_block_delta", {"type": "content_block_delta", "index": self.block_index,
                                                        "delta": {"type": "text_delta", "text": delta["content"]}}))

        for tc in delta.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name"):
                if self.block_open:
                    out.append(self._ev("content_block_stop", {"type": "content_block_stop", "index": self.block_index}))
                    self.block_index += 1
                out.append(self._ev("content_block_start", {"type": "content_block_start", "index": self.block_index,
                                                            "content_block": {"type": "tool_use",
                                                                              "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                                                                              "name": fn["name"], "input": {}}}))
                self.block_open = True
                self.tool_block = True
            if fn.get("arguments"):
                out.append(self._ev("content_block_delta", {"type": "content_block_delta", "index": self.block_index,
                                                            "delta": {"type": "input_json_delta", "partial_json": fn["arguments"]}}))

        if finish:
            out.extend(self.close(finish))
        return out

    def close(self, finish: str = "stop") -> list[str]:
        out: list[str] = []
        if self.closed:
            return out
        self.closed = True
        if self.block_open:
            out.append(self._ev("content_block_stop", {"type": "content_block_stop", "index": self.block_index}))
            self.block_open = False
        if self.started:
            stop_reason = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}.get(finish, "end_turn")
            out.append(self._ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason},
                                                  "usage": {"output_tokens": 0}}))
            out.append(self._ev("message_stop", {"type": "message_stop"}))
        return out


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
        health.record_fail(model)
        return None

    modified = copy.deepcopy(body)
    modified["model"] = model
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    anthropic_body = convert_request_openai_to_anthropic(modified)
    url = _build_endpoint(base_url, "/v1/messages")
    if not url:
        health.record_fail(model)
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
            health.record_success(model)
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
        health.record_fail(model)
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
        health.record_fail(model)
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
        health.record_fail(model)
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
            health.record_fail(model)
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
        health.record_success(model)
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

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


# ============================================================
# 请求转换：openai chat → Responses
# ============================================================

def _extract_text(content) -> str:
    """从 openai message content（字符串或块数组）提取纯文本"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def convert_request_openai_to_responses(body: dict) -> dict:
    """openai chat/completions 请求体 → Responses API 请求体"""
    out: dict = {"model": body.get("model", "")}
    instructions: list[str] = []
    input_items: list[dict] = []

    for msg in body.get("messages", []):
        role = msg.get("role", "")
        if role == "system":
            text = _extract_text(msg.get("content"))
            if text:
                instructions.append(text)
        elif role == "user":
            input_items.append({
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": _extract_text(msg.get("content"))}],
            })
        elif role == "assistant":
            text = _extract_text(msg.get("content"))
            if text:
                input_items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                })
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                input_items.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", ""),
                })
        elif role == "tool":
            input_items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": _extract_text(msg.get("content")),
            })

    if instructions:
        out["instructions"] = "\n".join(instructions)
    out["input"] = input_items

    if body.get("max_tokens") is not None:
        out["max_output_tokens"] = body["max_tokens"]
    for key in ("temperature", "top_p", "stream"):
        if body.get(key) is not None:
            out[key] = body[key]

    tools = []
    for t in body.get("tools") or []:
        fn = t.get("function", {})
        if fn.get("name"):
            tools.append({
                "type": "function",
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
    if tools:
        out["tools"] = tools
    return out


# ============================================================
# 响应转换：Responses → openai chat（非流式）
# ============================================================

def convert_response_responses_to_openai(data: dict, model: str) -> dict:
    """Responses API 响应 → openai chat/completions 响应"""
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    text_parts.append(str(c.get("text", "")))
        elif item.get("type") == "function_call":
            tool_calls.append({
                "id": item.get("call_id") or item.get("id", ""),
                "type": "function",
                "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "")},
            })

    message: dict = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls

    usage_in = data.get("usage") or {}
    prompt_tokens = usage_in.get("input_tokens", 0)
    completion_tokens = usage_in.get("output_tokens", 0)
    return {
        "id": data.get("id", "chatcmpl-resp"),
        "object": "chat.completion",
        "created": int(data.get("created_at", time.time())),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# ============================================================
# 流式转换：Responses SSE data 行 → openai SSE chunk
# ============================================================

def convert_responses_sse_data_to_openai(data: dict, model: str) -> str | None:
    """单个 Responses SSE data 载荷 → openai SSE 行（None 表示跳过该事件）"""
    etype = data.get("type", "")

    def chunk(delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
        obj = {
            "id": "chatcmpl-resp",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        if usage:
            obj["usage"] = usage
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    if etype == "response.created":
        return chunk({"role": "assistant"})
    if etype == "response.output_text.delta":
        return chunk({"content": data.get("delta", "")})
    if etype == "response.output_item.done":
        item = data.get("item") or {}
        if item.get("type") == "function_call":
            return chunk({"tool_calls": [{
                "index": 0,
                "id": item.get("call_id") or item.get("id", ""),
                "type": "function",
                "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "")},
            }]})
        return None
    if etype == "response.completed":
        resp = data.get("response") or {}
        usage_in = resp.get("usage") or {}
        usage = None
        if usage_in:
            pt, ct = usage_in.get("input_tokens", 0), usage_in.get("output_tokens", 0)
            usage = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
        has_tools = any(i.get("type") == "function_call" for i in resp.get("output") or [])
        return chunk({}, "tool_calls" if has_tools else "stop", usage)
    if etype in ("response.failed", "error"):
        err = json.dumps({"error": {"message": "upstream responses stream failed"}}, ensure_ascii=False)
        return f"data: {err}\n\ndata: [DONE]\n\n"
    return None


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
) -> StreamingResponse | None:
    """尝试流式请求到 Responses 格式上游，SSE 事件转 openai 格式（首字节分界线不变）"""
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
            resp = await http_client.send(
                http_client.build_request("POST", url, json=responses_body, headers=headers),
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


def _convert_sse_line(line: str, model: str) -> str | None:
    """单行 Responses SSE → openai chunk（只处理 data: 行，event:/空行跳过）"""
    if not line or not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    return convert_responses_sse_data_to_openai(data, model)


# ============================================================
# 入站逆转换（CH-010）：Responses → OpenAI
# ============================================================

def convert_request_responses_to_openai(body: dict) -> dict:
    """将 Responses API 请求体转换为 openai chat/completions 请求体（入站）"""
    messages: list[dict] = []

    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": str(instructions)})

    input_data = body.get("input")
    if isinstance(input_data, str):
        if input_data:
            messages.append({"role": "user", "content": input_data})
    elif isinstance(input_data, list):
        for item in input_data:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue
            itype = item.get("type", "message")
            if itype == "message":
                role = item.get("role", "user")
                parts: list[dict] = []
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text"):
                        parts.append({"type": "text", "text": str(c.get("text", ""))})
                    elif isinstance(c, dict) and c.get("type") == "input_image":
                        img_url = (c.get("image_url") or "").strip()
                        if img_url:
                            parts.append({"type": "image_url", "image_url": {"url": img_url}})
                    elif isinstance(c, str):
                        parts.append({"type": "text", "text": c})
                if len(parts) == 1 and parts[0]["type"] == "text":
                    content = parts[0]["text"]
                elif parts:
                    content = parts
                else:
                    content = item.get("content") if isinstance(item.get("content"), str) else ""
                if role == "system":
                    messages.insert(0, {"role": "system", "content": content})
                else:
                    messages.append({"role": role, "content": content})
            elif itype == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": item.get("call_id") or item.get("id", ""),
                        "type": "function",
                        "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "")},
                    }],
                })
            elif itype == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": str(item.get("output", "")),
                })

    result: dict = {"model": body.get("model", ""), "messages": messages}
    if body.get("max_output_tokens") is not None:
        result["max_tokens"] = body["max_output_tokens"]
    for key in ("temperature", "top_p", "stream"):
        if body.get(key) is not None:
            result[key] = body[key]
    if body.get("tools"):
        result["tools"] = [
            {"type": "function", "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            }}
            for t in body["tools"] if t.get("name")
        ]
    return result


def convert_response_openai_to_responses(openai_resp: dict, model: str) -> dict:
    """将 openai chat/completions 响应转换为 Responses API 响应（入站）"""
    choice = (openai_resp.get("choices") or [{}])[0]
    message = choice.get("message", {})
    output: list[dict] = []
    # 推理模型（deepseek 系）reasoning → Responses reasoning item，避免只回推理时正文为空
    reasoning = message.get("reasoning")
    if not reasoning and message.get("reasoning_details"):
        reasoning = "".join(
            str(d.get("text", "")) for d in message["reasoning_details"]
            if isinstance(d, dict) and d.get("text")
        )
    if reasoning:
        output.append({
            "type": "reasoning",
            "id": f"rs_{int(time.time() * 1000)}",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": reasoning}],
        })
    if message.get("content"):
        output.append({
            "type": "message",
            "id": f"msg_{int(time.time() * 1000)}",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": message["content"]}],
        })
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        output.append({
            "type": "function_call",
            "id": f"fc_{int(time.time() * 1000)}",
            "call_id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "arguments": fn.get("arguments", ""),
            "status": "completed",
        })

    usage_in = openai_resp.get("usage") or {}
    pt, ct = usage_in.get("prompt_tokens", 0), usage_in.get("completion_tokens", 0)
    return {
        "id": f"resp_{int(time.time() * 1000)}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {"input_tokens": pt, "output_tokens": ct, "total_tokens": pt + ct},
    }


class OpenaiToResponsesSSE:
    """openai SSE chunk → Responses SSE 事件序列（入站流式状态机，CH-010）"""

    def __init__(self, model: str):
        self.model = model
        self.started = False
        self.item_added = False
        self.text_parts: list[str] = []
        self.reasoning_parts: list[str] = []
        self.reasoning_item_started = False
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
            out.append(self._ev("response.failed", {"type": "response.failed", "response": {"status": "failed",
                                "error": {"message": str(data["error"])}}}))
            out.extend(self.close())
            return out

        choice = (data.get("choices") or [{}])[0]
        delta = choice.get("delta", {})
        finish = choice.get("finish_reason")

        if not self.started:
            self.started = True
            out.append(self._ev("response.created", {"type": "response.created", "response": {
                "id": f"resp_{int(time.time() * 1000)}", "object": "response", "status": "in_progress",
                "model": self.model, "output": []}}))

        # 推理内容（deepseek 系 delta.reasoning_content / 部分上游用 delta.reasoning）→ reasoning item + summary delta
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            if not self.reasoning_item_started:
                self.reasoning_item_started = True
                out.append(self._ev("response.output_item.added", {"type": "response.output_item.added",
                                    "output_index": 0, "item": {"type": "reasoning", "status": "in_progress",
                                                                 "summary": []}}))
            self.reasoning_parts.append(reasoning)
            out.append(self._ev("response.reasoning_summary_text.delta", {
                "type": "response.reasoning_summary_text.delta",
                "output_index": 0, "item_id": f"rs_{int(time.time() * 1000)}",
                "summary_index": 0, "delta": reasoning}))

        if delta.get("content"):
            if self.reasoning_item_started and not self.item_added:
                out.append(self._ev("response.output_item.done", {"type": "response.output_item.done",
                                    "output_index": 0, "item": {"type": "reasoning", "status": "completed",
                                                                 "summary": [{"type": "summary_text",
                                                                              "text": "".join(self.reasoning_parts)}]}}))
            if not self.item_added:
                self.item_added = True
                out.append(self._ev("response.output_item.added", {"type": "response.output_item.added",
                                    "output_index": 1, "item": {"type": "message", "role": "assistant", "status": "in_progress"}}))
            self.text_parts.append(delta["content"])
            out.append(self._ev("response.output_text.delta", {"type": "response.output_text.delta",
                                "output_index": 1, "content_index": 0, "delta": delta["content"]}))

        for tc in delta.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name"):
                out.append(self._ev("response.output_item.done", {"type": "response.output_item.done",
                                    "output_index": 2, "item": {"type": "function_call", "status": "completed",
                                                                "call_id": tc.get("id", ""), "name": fn["name"],
                                                                "arguments": fn.get("arguments", "")}}))

        if finish:
            out.extend(self.close())
        return out

    def close(self) -> list[str]:
        out: list[str] = []
        if self.closed:
            return out
        self.closed = True
        if self.reasoning_item_started and not self.item_added:
            out.append(self._ev("response.output_item.done", {"type": "response.output_item.done", "output_index": 0,
                                "item": {"type": "reasoning", "status": "completed",
                                         "summary": [{"type": "summary_text", "text": "".join(self.reasoning_parts)}]}}))
        if self.item_added:
            out.append(self._ev("response.output_item.done", {"type": "response.output_item.done", "output_index": 1,
                                "item": {"type": "message", "role": "assistant", "status": "completed",
                                         "content": [{"type": "output_text", "text": "".join(self.text_parts)}]}}))
        if self.started:
            output: list[dict] = []
            if self.reasoning_parts:
                output.append({"type": "reasoning", "status": "completed",
                               "summary": [{"type": "summary_text", "text": "".join(self.reasoning_parts)}]})
            if self.text_parts:
                output.append({"type": "message", "role": "assistant", "status": "completed",
                               "content": [{"type": "output_text", "text": "".join(self.text_parts)}]})
            out.append(self._ev("response.completed", {"type": "response.completed", "response": {
                "id": f"resp_{int(time.time() * 1000)}", "object": "response", "status": "completed",
                "model": self.model, "output": output}}))
        return out


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

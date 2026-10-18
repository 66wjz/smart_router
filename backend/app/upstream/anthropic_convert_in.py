"""
Anthropic → OpenAI 入站逆转换（CH-026，原 CH-009 逻辑）

把 Anthropic 请求转成 OpenAI 请求、把 OpenAI 响应/SSE 转回 Anthropic 格式。
出站正向转换见 anthropic_convert.py。
"""

import json
import logging
import time
import uuid
from typing import Any

log = logging.getLogger("router")


# ============================================================
# 入站逆转换（CH-009）：Anthropic → OpenAI
# ============================================================

def _anthropic_image_block_to_openai(block: dict) -> dict | None:
    """anthropic image 块 → openai image_url 块（base64 → data URI / url 直传）"""
    source = block.get("source") or {}
    stype = source.get("type", "")
    if stype == "base64":
        data = source.get("data", "")
        if not data:
            return None
        media = source.get("media_type", "image/png")
        return {"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}}
    if stype == "url":
        url = source.get("url", "")
        if not url:
            return None
        return {"type": "image_url", "image_url": {"url": url}}
    return None


def _anthropic_content_to_openai(content) -> tuple[str | list, list[dict], list[dict]]:
    """解析 anthropic message content → (content, tool_calls, tool_results)
    content 为纯文本字符串（无图片时）或 openai 多模态块列表（含图片时）"""
    if isinstance(content, str):
        return content, [], []
    openai_parts: list[dict] = []
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            openai_parts.append({"type": "text", "text": str(block.get("text", ""))})
        elif btype == "image":
            img = _anthropic_image_block_to_openai(block)
            if img:
                openai_parts.append(img)
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
    if not openai_parts:
        return "", tool_calls, tool_results
    if len(openai_parts) == 1 and openai_parts[0]["type"] == "text":
        return openai_parts[0]["text"], tool_calls, tool_results
    return openai_parts, tool_calls, tool_results


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
        content, tool_calls, tool_results = _anthropic_content_to_openai(msg.get("content"))
        if tool_results:
            for tr in tool_results:
                messages.append({"role": "tool", "tool_call_id": tr["tool_call_id"], "content": tr["content"]})
        entry: dict = {"role": role, "content": content}
        if tool_calls:
            entry["tool_calls"] = tool_calls
        if content or tool_calls:
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
    # 推理模型（deepseek 系）的 reasoning 内容 → anthropic thinking 块，避免只回 reasoning 时正文为空
    reasoning = message.get("reasoning")
    if not reasoning and message.get("reasoning_details"):
        reasoning = "".join(
            str(d.get("text", "")) for d in message["reasoning_details"]
            if isinstance(d, dict) and d.get("text")
        )
    if reasoning:
        content.append({"type": "thinking", "thinking": reasoning})
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
    if not content:
        content.append({"type": "text", "text": ""})

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
        self.block_type: str | None = None  # None / "thinking" / "text" / "tool"
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

        # 推理内容（deepseek 系 delta.reasoning_content / 部分上游用 delta.reasoning）→ thinking 块
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            if self.block_open and self.block_type != "thinking":
                out.append(self._ev("content_block_stop", {"type": "content_block_stop", "index": self.block_index}))
                self.block_open = False
                self.block_index += 1
            if not self.block_open:
                out.append(self._ev("content_block_start", {"type": "content_block_start", "index": self.block_index,
                                                            "content_block": {"type": "thinking", "thinking": ""}}))
                self.block_open = True
                self.block_type = "thinking"
            out.append(self._ev("content_block_delta", {"type": "content_block_delta", "index": self.block_index,
                                                        "delta": {"type": "thinking_delta", "thinking": reasoning}}))

        if delta.get("content"):
            if self.block_open and self.block_type != "text":
                out.append(self._ev("content_block_stop", {"type": "content_block_stop", "index": self.block_index}))
                self.block_open = False
                self.block_index += 1
            if not self.block_open:
                out.append(self._ev("content_block_start", {"type": "content_block_start", "index": self.block_index,
                                                            "content_block": {"type": "text", "text": ""}}))
                self.block_open = True
                self.block_type = "text"
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
                self.block_type = "tool"
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

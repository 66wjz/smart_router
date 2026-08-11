"""CH-012/CH-014 验证用 mock 上游：可编程失败 + openai/responses 双端点

控制：
  GET /__set?fails=2&status=500  → 接下来 2 次请求返回 500，之后恢复 200
  GET /__count                   → /v1/chat/completions 请求数
  GET /__respcount               → /v1/responses 请求数
  GET /__last                    → 最近一次收到的请求体（断言转换格式用）
  GET /__reset                   → 计数与失败状态清零
业务：
  POST /v1/chat/completions      → openai 兼容响应
  POST /v1/responses             → Responses 兼容响应（stream:true 时发 SSE 事件序列）
"""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

state = {"fails_left": 0, "status": 500, "count": 0, "resp_count": 0, "last_body": None}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _maybe_fail(self) -> bool:
        if state["fails_left"] > 0:
            state["fails_left"] -= 1
            self._send(state["status"], {"error": {"message": f"mock {state['status']}"}})
            return True
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/__set":
            q = parse_qs(parsed.query)
            state["fails_left"] = int(q.get("fails", ["0"])[0])
            state["status"] = int(q.get("status", ["500"])[0])
            self._send(200, {"ok": True})
        elif parsed.path == "/__count":
            self._send(200, {"count": state["count"]})
        elif parsed.path == "/__respcount":
            self._send(200, {"count": state["resp_count"]})
        elif parsed.path == "/__last":
            self._send(200, state["last_body"] or {})
        elif parsed.path == "/__reset":
            state.update({"count": 0, "resp_count": 0, "fails_left": 0, "last_body": None})
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "unknown"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            req_body = json.loads(raw or b"{}")
        except Exception:
            req_body = {}
        state["last_body"] = req_body

        if path == "/v1/chat/completions":
            state["count"] += 1
            if self._maybe_fail():
                return
            if req_body.get("stream"):
                self._send_openai_sse(req_body.get("model", "mock-m1"))
                return
            self._send(200, {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "mock 回复"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
        elif path == "/v1/responses":
            state["resp_count"] += 1
            if self._maybe_fail():
                return
            if req_body.get("stream"):
                self._send_responses_sse()
            else:
                self._send(200, {
                    "id": "resp-mock",
                    "object": "response",
                    "created_at": int(time.time()),
                    "status": "completed",
                    "output": [{
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "mock responses 回复"}],
                    }],
                    "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                })
        else:
            self._send(404, {"error": "unknown"})

    def _send_responses_sse(self):
        events = [
            {"type": "response.created", "response": {"id": "resp-mock"}},
            {"type": "response.output_text.delta", "delta": "mock "},
            {"type": "response.output_text.delta", "delta": "流式回复"},
            {"type": "response.completed", "response": {
                "id": "resp-mock",
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": "mock 流式回复"}]}],
                "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
            }},
        ]
        payload = b""
        for ev in events:
            payload += f"event: {ev['type']}\n".encode()
            payload += f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_openai_sse(self, model: str):
        def chunk(delta, finish=None):
            obj = {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                   "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()
        payload = chunk({"role": "assistant"})
        payload += chunk({"content": "mock "})
        payload += chunk({"content": "流式回复"})
        payload += chunk({}, "stop")
        payload += b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18099), Handler).serve_forever()

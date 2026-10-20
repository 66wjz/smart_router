"""CH-039 验证：流式 usage chunk 是否按客户端意图透传

用法：python test/verify_usage_passthrough_ch039.py

覆盖：
    1. 客户端【不传】include_usage → 仍可用（注入 + 剥离，保持旧行为）
    2. 客户端【传】include_usage   → 必须收到 usage chunk（本次修复点）
    3. 两种情况服务端都正确记账（estimated=0、token 数值正确）
    4. 流式正文内容不被破坏（两个 delta 都在）
    5. 非流式不受影响（仍从响应体取 usage）

不依赖外网；临时库，跑完即删。
"""

import json
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

failures: list[str] = []

PROMPT_TOKENS = 1234
COMPLETION_TOKENS = 56
CACHED_TOKENS = 800


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


class MockUpstream(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        wants_usage = bool((payload.get("stream_options") or {}).get("include_usage"))

        if not payload.get("stream"):
            body = json.dumps({
                "id": "x", "object": "chat.completion",
                "choices": [{"index": 0,
                             "message": {"role": "assistant", "content": "hello"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": PROMPT_TOKENS,
                          "completion_tokens": COMPLETION_TOKENS,
                          "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
                          "prompt_tokens_details": {"cached_tokens": CACHED_TOKENS}},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i in range(2):
            chunk = {
                "id": "x", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": f"t{i}"},
                             "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        if wants_usage:
            usage_chunk = {
                "id": "x", "object": "chat.completion.chunk",
                "choices": [],
                "usage": {"prompt_tokens": PROMPT_TOKENS,
                          "completion_tokens": COMPLETION_TOKENS,
                          "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
                          "prompt_tokens_details": {"cached_tokens": CACHED_TOKENS}},
            }
            self.wfile.write(f"data: {json.dumps(usage_chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *args):
        pass


def build_app(db_path: str, port: int):
    os.environ["SMART_ROUTER_DB"] = db_path
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    import sqlite3
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    sql_root = os.path.join(ROOT, "sql")
    files = [
        "01_建表.sql",
        "increment/01_增量_20260809_上游源禁用.sql",
        "increment/02_增量_20260809_上游Key池.sql",
        "increment/03_增量_20260809_上游模型列表.sql",
        "increment/04_增量_20260810_智能重试开关.sql",
        "increment/05_增量_20260811_上游多分组.sql",
        "06_用量统计与自动聚合.sql",
        "increment/06_增量_20261017_聚合探测配置.sql",
        "increment/07_增量_20261017_聚合统一与探测模板.sql",
        "increment/08_增量_20261017_聚合规则绑定.sql",
        "increment/09_增量_20261018_聚合分组.sql",
        "increment/10_增量_20261018_自动聚合开关默认关闭.sql",
        "increment/11_增量_20261019_请求详情可观测性.sql",
    ]
    for rel in files:
        path = os.path.join(sql_root, rel.replace("/", os.sep))
        with open(path, encoding="utf-8") as f:
            try:
                conn.executescript(f.read())
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
    conn.commit()
    conn.close()

    from app.core.config import config
    from app.main import app
    from app.repositories.api_key_repo import ApiKeyRepository

    config.add_upstream({
        "id": "mock", "name": "mock", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock", "format": "openai", "groups": ["free"],
        "probe_enabled": False, "models": [{"name": "mock-model", "enabled": True}],
    })
    ApiKeyRepository().create("t", "sk-test-ch039", '["free"]', True)
    config.reload()
    return app


def parse_usage(raw: str) -> dict | None:
    """从 SSE 文本里找带 usage 的 chunk"""
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("usage"):
            return data["usage"]
    return None


def last_usage_row(app):
    from app.repositories.usage_repo import UsageRepository
    rows = UsageRepository().query(
        "SELECT prompt_tokens, completion_tokens, total_tokens, estimated, "
        "cache_read_tokens, stream FROM log_usage ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else {}


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch039")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)

    from starlette.testclient import TestClient
    client = TestClient(app)
    headers = {"Authorization": "Bearer sk-test-ch039"}

    # ---------------- A：客户端不要求 usage ----------------
    print("\n[1] 客户端【不传】include_usage → 旧行为（注入后剥离）")
    with client.stream("POST", "/v1/chat/completions", headers=headers, json={
        "model": "mock-model", "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    }) as r:
        raw_a = b"".join(r.iter_bytes()).decode("utf-8", "ignore")
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    check(parse_usage(raw_a) is None, "客户端未要求 → 不返回 usage chunk（保持兼容）")
    check("t0" in raw_a and "t1" in raw_a, "正文两个 delta 都在")
    app.state.usage_buffer.flush()
    row_a = last_usage_row(app)
    check(row_a.get("prompt_tokens") == PROMPT_TOKENS,
          f"服务端仍正确记账 prompt={row_a.get('prompt_tokens')}")
    check(row_a.get("estimated") == 0, "非估算（确实解析到 usage）")
    check(row_a.get("cache_read_tokens") == CACHED_TOKENS,
          f"缓存 token 已记录（{row_a.get('cache_read_tokens')}）")

    # ---------------- B：客户端要求 usage（DSH 场景） ----------------
    print("\n[2] 客户端【传】include_usage=true → 必须收到 usage（本次修复点）")
    with client.stream("POST", "/v1/chat/completions", headers=headers, json={
        "model": "mock-model", "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [{"role": "user", "content": "hi"}],
    }) as r:
        raw_b = b"".join(r.iter_bytes()).decode("utf-8", "ignore")
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    usage_b = parse_usage(raw_b)
    check(usage_b is not None, "客户端要求 → 收到 usage chunk")
    if usage_b:
        check(usage_b.get("prompt_tokens") == PROMPT_TOKENS,
              f"prompt_tokens 正确（{usage_b.get('prompt_tokens')}）")
        check(usage_b.get("completion_tokens") == COMPLETION_TOKENS,
              f"completion_tokens 正确（{usage_b.get('completion_tokens')}）")
        check(usage_b.get("total_tokens") == PROMPT_TOKENS + COMPLETION_TOKENS,
              f"total_tokens 正确（{usage_b.get('total_tokens')}）")
        cached = (usage_b.get("prompt_tokens_details") or {}).get("cached_tokens")
        check(cached == CACHED_TOKENS, f"缓存字段透传（{cached}）")
    check("t0" in raw_b and "t1" in raw_b, "正文两个 delta 都在（未被破坏）")
    app.state.usage_buffer.flush()
    row_b = last_usage_row(app)
    check(row_b.get("prompt_tokens") == PROMPT_TOKENS, "服务端记账不受影响")

    # ---------------- C：非流式不受影响 ----------------
    print("\n[3] 非流式不受影响")
    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": "mock-model",
        "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, "返回 200")
    body = r.json()
    check((body.get("usage") or {}).get("prompt_tokens") == PROMPT_TOKENS,
          "非流式 usage 原样透传")
    app.state.usage_buffer.flush()
    row_c = last_usage_row(app)
    check(row_c.get("stream") == 0, "非流式记录 stream=0")
    check(row_c.get("cache_read_tokens") == CACHED_TOKENS, "非流式缓存 token 已记录")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

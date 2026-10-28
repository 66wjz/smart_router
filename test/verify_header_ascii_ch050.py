"""CH-050 验证：中文上游源 ID 不能把 /v1 响应打成 500（UnicodeEncodeError）

用法：python test/verify_header_ascii_ch050.py

背景：
    上游源 ID 允许中文（历史数据里有「星-国模013」「星-国产模型」）。旧版把
    `f"{upstream_id}/{model}"` 原样写进响应头 X-Served-By；HTTP 头只能是 latin-1，
    Starlette 构造 JSONResponse/StreamingResponse 时抛 UnicodeEncodeError，最终被
    全局兜底成 500「中转站内部错误: UnicodeEncodeError」。上游源页的「测试」走
    test_non_stream（不带 X-Served-By），所以单测正常、接入 /v1（尤其聚合）才炸。

覆盖：
    1. ascii_header_value / ascii_safe_headers：纯 ASCII 不变、中文 percent-encode
    2. _RetryLoop.response_headers()：中文 id 也能被 latin-1 编码
    3. 非流式 /v1/chat/completions（聚合 test_demo）→ 200，X-Served-By 为 ASCII
    4. 流式 /v1/chat/completions（聚合 test_demo）→ 200，正文完整
    5. 直连模型（中文 id 上游）→ 200
    6. /v1/messages（Anthropic 入站）→ 200，X-Served-By 为 ASCII

不依赖外网；临时库，跑完即删。
"""

import json
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

failures: list[str] = []

CN_UPSTREAM = "星-国模013"
MODEL = "deepseek-flash"
AGG = "test_demo"


class MockUpstream(BaseHTTPRequestHandler):
    """正常 chat/completions 上游：按 stream 返回 JSON 或 SSE"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        stream = bool(payload.get("stream"))
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(2):
                chunk = {"id": "x", "object": "chat.completion.chunk",
                         "choices": [{"index": 0, "delta": {"content": f"t{i}"},
                                      "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            usage = {"id": "x", "object": "chat.completion.chunk", "choices": [],
                     "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        body = json.dumps({
            "id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # 上游自己也回一个中文头 —— 本系统不透传上游头，顺便验证不会串到客户端
        self.send_header("X-Upstream-Note", CN_UPSTREAM.encode("utf-8").decode("latin-1"))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


SQL_FILES = [
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
    "increment/12_增量_20261021_请求过滤引擎.sql",
]


def build_app(db_path: str, port: int):
    os.environ["SMART_ROUTER_DB"] = db_path
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    import sqlite3
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    for rel in SQL_FILES:
        path = os.path.join(ROOT, "sql", rel.replace("/", os.sep))
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
    from app.repositories.aggregation_repo import AggregationRepository

    # 中文 ID 上游（复刻用户现场）
    config.add_upstream({
        "id": CN_UPSTREAM, "name": CN_UPSTREAM, "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock-cn", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": MODEL, "enabled": True}],
    })
    ApiKeyRepository().create("t", "sk-test-ch050", '["free"]', True)
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [{"upstream": CN_UPSTREAM, "model": MODEL, "weight": 1}],
        "sort_mode": "stable", "remark": "CH-050 中文 ID 聚合验证",
    })
    config.reload()
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    from app.main import health as _health
    _health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch050")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)

    # ---------- 1. 单元：头值安全化 ----------
    print("\n[1] ascii_header_value / ascii_safe_headers")
    from app.upstream.headers import ascii_header_value, ascii_safe_headers
    check(ascii_header_value("src_good/deepseek-flash") == "src_good/deepseek-flash",
          "纯 ASCII 原样返回（行为零变化）")
    enc = ascii_header_value(f"{CN_UPSTREAM}/{MODEL}")
    check(enc.isascii(), f"中文 id 编码后纯 ASCII（{enc}）")
    check(unquote(enc) == f"{CN_UPSTREAM}/{MODEL}", "percent-encode 可逆")
    safe = ascii_safe_headers({"X-A": CN_UPSTREAM, "X-B": "plain"})
    check(all(str(v).isascii() for v in safe.values()), "ascii_safe_headers 全 ASCII")
    check(safe["X-B"] == "plain", "ASCII 值不被改写")

    # ---------- 2. 单元：_RetryLoop 响应头 ----------
    print("\n[2] _RetryLoop.response_headers()（四种适配器共用）")
    from app.upstream.openai_adapter import _RetryLoop
    from app.core.config import config
    rl = _RetryLoop(config, CN_UPSTREAM, MODEL, ["sk-mock-cn"])
    hdrs = rl.response_headers()
    check(all(str(v).isascii() for v in hdrs.values()),
          f"响应头全 ASCII（{hdrs}）")
    from starlette.responses import JSONResponse
    try:
        JSONResponse(status_code=200, content={}, headers=hdrs)
        ok = True
    except Exception as e:
        ok = False
        print("   ", type(e).__name__, e)
    check(ok, "JSONResponse 构造不再抛 UnicodeEncodeError")

    # ---------- 3. 非流式聚合 ----------
    from starlette.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    auth = {"Authorization": "Bearer sk-test-ch050"}
    print("\n[3] 非流式 /v1/chat/completions（聚合 test_demo）")
    r = client.post("/v1/chat/completions", headers=auth, json={
        "model": AGG, "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    if r.status_code != 200:
        print("   body:", r.text[:300])
    served = r.headers.get("x-served-by", "")
    check(bool(served) and served.isascii(), f"X-Served-By 存在且 ASCII（{served}）")
    check(unquote(served) == f"{CN_UPSTREAM}/{MODEL}", "X-Served-By 可还原成中文 id/模型")

    # ---------- 4. 流式聚合 ----------
    print("\n[4] 流式 /v1/chat/completions（聚合 test_demo）")
    with client.stream("POST", "/v1/chat/completions", headers=auth, json={
        "model": AGG, "stream": True, "messages": [{"role": "user", "content": "hi"}],
    }) as resp:
        raw = b"".join(resp.iter_bytes()).decode("utf-8", "ignore")
        st = resp.status_code
        served_s = resp.headers.get("x-served-by", "")
    check(st == 200, f"返回 200（实际 {st}）")
    check("t0" in raw and "t1" in raw, "流式正文完整")
    check("[DONE]" in raw, "SSE 正常收尾")
    check(served_s.isascii() and bool(served_s), f"流式响应头 ASCII（{served_s}）")

    # ---------- 5. 直连（中文 id 上游的模型） ----------
    print("\n[5] 直连模型 deepseek-flash（同一中文 id 上游）")
    r = client.post("/v1/chat/completions", headers=auth, json={
        "model": MODEL, "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    check(r.headers.get("x-served-by", "").isascii(), "直连也带 ASCII 头")

    # ---------- 6. Anthropic 入站 ----------
    print("\n[6] /v1/messages（Anthropic 入站，聚合 test_demo）")
    r = client.post("/v1/messages", headers=auth, json={
        "model": AGG, "max_tokens": 64,
        "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    if r.status_code != 200:
        print("   body:", r.text[:300])
    served_m = r.headers.get("x-served-by", "")
    check(served_m.isascii() and bool(served_m), f"X-Served-By ASCII（{served_m}）")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

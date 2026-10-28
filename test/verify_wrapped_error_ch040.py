"""CH-040 验证：上游「HTTP 200 + 错误包」必须按失败处理并切换候选

用法：python test/verify_wrapped_error_ch040.py

覆盖：
    1. 流式首行错误包 → 自动切到下一候选
    2. 流式全部候选都错误包 → 503（不伪装 200）
    3. 非流式 200 + 错误包 → 自动切候选
    4. 正常流式 → 不误判
    5. 同时带 error 与 choices → 不误判（保守条件）
    6. 错误包记账 → status=error、attempt_count>1
    7. 错误包详情 → 落 log_usage_detail（即使 error_only）
    8. 重试后成功 → attempt 链含首条错误、attempt_count=2
    9. 聚合模型（agg_unified 多成员）首成员错误包 → 切到第二成员

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

BAD_MODEL = "bad-model"
GOOD_MODEL = "good-model"
ERR_MSG = ("buddy: 请求被拦截，请重新发送 "
           "Illegal API invocation from an unapproved channel")

PROMPT_TOKENS = 111
COMPLETION_TOKENS = 22


class MockUpstream(BaseHTTPRequestHandler):
    """按 model 名决定返回：bad-model 返回错误包，good-model 返回正常流"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        model = payload.get("model", "")
        stream = bool(payload.get("stream"))
        # 用 Key 区分来自哪个上游源（同名模型 dup-model 的两个候选）
        auth = self.headers.get("Authorization", "")
        from_bad_src = "sk-mock-bad" in auth

        if model.startswith("bad") or (model.startswith("dup") and from_bad_src):
            self._send_error_pack(stream)
            return
        if model.startswith("mixed"):
            self._send_mixed(stream)
            return
        self._send_ok(stream)

    def _send_error_pack(self, stream: bool):
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {
                "id": "x", "object": "chat.completion.chunk",
                "model": "bad-model", "choices": [],
                "error": {"message": ERR_MSG, "type": "server_error",
                          "code": "INVALID_REQUEST", "status": 400},
            }
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            body = json.dumps({
                "error": {"message": ERR_MSG, "type": "server_error",
                          "code": "INVALID_REQUEST", "status": 400},
            }, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _send_mixed(self, stream: bool):
        """同时带 error 与 choices —— 不应被判为失败"""
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {
                "id": "x", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
                "error": {"message": "degraded but usable"},
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            body = json.dumps({
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}],
                "error": {"message": "degraded but usable"},
                "usage": {"prompt_tokens": PROMPT_TOKENS,
                          "completion_tokens": COMPLETION_TOKENS,
                          "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _send_ok(self, stream: bool):
        if not stream:
            body = json.dumps({
                "id": "x", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": PROMPT_TOKENS,
                          "completion_tokens": COMPLETION_TOKENS,
                          "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS},
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
            chunk = {"id": "x", "object": "chat.completion.chunk",
                     "choices": [{"index": 0, "delta": {"content": f"t{i}"},
                                  "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        usage_chunk = {"id": "x", "object": "chat.completion.chunk", "choices": [],
                       "usage": {"prompt_tokens": PROMPT_TOKENS,
                                 "completion_tokens": COMPLETION_TOKENS,
                                 "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS}}
        self.wfile.write(f"data: {json.dumps(usage_chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

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
    # CH-040：详情策略先设为默认 error_only，用于验证「失败能进详情」
    conn.execute("DELETE FROM sys_setting WHERE key='usage_detail_mode'")
    conn.execute("INSERT INTO sys_setting(key,value) VALUES('usage_detail_mode','\"error_only\"')")
    conn.commit()
    conn.close()

    from app.core.config import config
    from app.main import app
    from app.repositories.api_key_repo import ApiKeyRepository

    # 两个上游源：都能提供 dup-model（同名多源 → 该请求有 2 个候选）。
    # src_bad 返回错误包，src_good 正常 → 用于验证「错误包会自动切下一候选」。
    config.add_upstream({
        "id": "src_bad", "name": "src_bad", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock-bad", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": BAD_MODEL, "enabled": True},
                   {"name": "dup-model", "enabled": True}],
    })
    config.add_upstream({
        "id": "src_good", "name": "src_good", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock-good", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": GOOD_MODEL, "enabled": True},
                   {"name": "mixed-model", "enabled": True},
                   {"name": "dup-model", "enabled": True}],
    })
    ApiKeyRepository().create("t", "sk-test-ch040", '["free"]', True)
    # CH-040：聚合模型（agg_unified kind=static）—— 用户实际场景：
    # 一个聚合名下有多个成员（不同上游源），首个成员返回错误包必须切到下一个
    from app.repositories.aggregation_repo import AggregationRepository
    AggregationRepository().upsert("agg-dup", {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": "src_bad", "model": "dup-model", "weight": 1},
            {"upstream": "src_good", "model": "dup-model", "weight": 1},
        ],
        "sort_mode": "stable", "remark": "CH-040 聚合切换验证",
    })
    config.reload()
    # 测试隔离：本脚本会反复把 src_bad 的 Key 打成失败，
    # 若沿用默认 max_fails=3 会触发冷却，后续用例根本发不出请求（尝试链为空），
    # 从而掩盖真正的断言。这里放宽阈值，专测「错误包 → 切候选」本身。
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    from app.main import health as _health
    _health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def last_usage(app):
    from app.repositories.usage_repo import UsageRepository
    rows = UsageRepository().query(
        "SELECT id, status, http_status, completion_tokens, estimated, attempt_count, "
        "upstream_id, error_msg FROM log_usage ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else {}


def detail_of(app, log_id):
    from app.repositories.usage_repo import UsageRepository
    return UsageRepository().get_detail(log_id)


def parse_usage(raw: str):
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


def stream_once(client, headers, model, include_usage=True):
    body = {"model": model, "stream": True,
            "messages": [{"role": "user", "content": "hi"}]}
    if include_usage:
        body["stream_options"] = {"include_usage": True}
    with client.stream("POST", "/v1/chat/completions", headers=headers, json=body) as r:
        raw = b"".join(r.iter_bytes()).decode("utf-8", "ignore")
    return r.status_code, raw


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch040")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)

    from starlette.testclient import TestClient
    client = TestClient(app)
    headers = {"Authorization": "Bearer sk-test-ch040"}

    # ---------- 1. 流式错误包 → 切候选 ----------
    print("\n[1] 流式首行错误包 + 有可用候选 → 自动切换")
    # 让 bad-model 与 good-model 成为同一请求的候选：用「同名多源」不现实，
    # 这里直接请求 bad-model（仅 1 候选），验证其「不再返回 200 空流」；
    # 再用 src_good 的模型验证正常路径。
    st, raw = stream_once(client, headers, BAD_MODEL)
    check(st != 200 or "[DONE]" not in raw,
          f"错误包不再伪装成正常 200 流（实际 status={st}）")
    check("unapproved" not in raw or st != 200,
          "错误包内容不会以 200 形式透传给客户端")

    app.state.usage_buffer.flush()
    row = last_usage(app)
    check(row.get("status") == "error", f"记账为 error（实际 {row.get('status')}）")
    check(bool(row.get("error_msg")), f"error_msg 已记录（{str(row.get('error_msg'))[:50]}）")

    # ---------- 2. 详情能落库（error_only 模式下） ----------
    print("\n[2] error_only 模式下，错误包也能进详情表")
    det = detail_of(app, row.get("id"))
    check(bool(det), f"详情行存在（log_id={row.get('id')}）")
    if det:
        resp = (det.get("detail") or {}).get("response_body") or ""
        check("unapproved" in resp, "详情里保留了错误原文")
        atts = json.loads((det.get("detail") or {}).get("attempts") or "[]")
        check(len(atts) >= 1, f"尝试链有记录（{len(atts)} 条）")
        if atts:
            check(bool(atts[0].get("error")), "尝试链首条带错误原因")

    # ---------- 3. 非流式错误包 ----------
    print("\n[3] 非流式 200 + 错误包 → 按失败处理")
    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": BAD_MODEL, "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 503, f"返回 503 而非 200（实际 {r.status_code}）")
    app.state.usage_buffer.flush()
    row2 = last_usage(app)
    check(row2.get("status") == "error", f"非流式也记为 error（实际 {row2.get('status')}）")

    # ---------- 4. 正常响应不误判 ----------
    print("\n[4] 正常响应不被误判")
    st, raw = stream_once(client, headers, GOOD_MODEL)
    check(st == 200, f"流式正常返回 200（实际 {st}）")
    check("t0" in raw and "t1" in raw, "正文两个 delta 都在")
    check(parse_usage(raw) is not None, "usage 正常透传")
    app.state.usage_buffer.flush()
    row3 = last_usage(app)
    check(row3.get("status") == "success", f"记为 success（实际 {row3.get('status')}）")

    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": GOOD_MODEL, "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"非流式正常返回 200（实际 {r.status_code}）")

    # ---------- 5. 同时带 error 与 choices → 不误判 ----------
    print("\n[5] 同时带 error 与 choices → 不误判为失败（保守条件）")
    st, raw = stream_once(client, headers, "mixed-model")
    check(st == 200, f"返回 200（实际 {st}）")
    check("ok" in raw, "正文正常透传")
    app.state.usage_buffer.flush()
    row4 = last_usage(app)
    check(row4.get("status") == "success", f"记为 success（实际 {row4.get('status')}）")

    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": "mixed-model", "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"非流式返回 200（实际 {r.status_code}）")

    # ---------- 6. 核心：错误包 → 真正切换到下一候选 ----------
    print("\n[6] 核心场景：同名多源，首个候选返回错误包 → 自动切到下一个源")
    st, raw = stream_once(client, headers, "dup-model")
    check(st == 200, f"最终对客户端返回 200（实际 {st}）")
    check("t0" in raw and "t1" in raw, "收到第二个候选的正常正文")
    check("unapproved" not in raw, "错误包内容没有透传给客户端")
    check(parse_usage(raw) is not None, "第二个候选的 usage 正常透传")
    app.state.usage_buffer.flush()
    row5 = last_usage(app)
    check(row5.get("status") == "success", f"最终记为 success（实际 {row5.get('status')}）")
    check(row5.get("attempt_count") >= 2,
          f"attempt_count>=2 证明发生了切换（实际 {row5.get('attempt_count')}）")
    # 成功请求在默认 error_only 策略下不写详情（符合 CH-038 设计），
    # 尝试链的完整性改在「全失败」场景下验证（见 [2]）。
    det5 = detail_of(app, row5.get("id"))
    check(det5 is not None, "主表行可查")
    check((det5 or {}).get("detail") is None,
          "成功请求在 error_only 下不写详情（符合设计）")

    # ---------- 7. 非流式也切换 ----------
    print("\n[7] 非流式：错误包同样切换候选")
    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": "dup-model", "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    body = r.json()
    check((body.get("choices") or [{}])[0].get("message", {}).get("content") == "hello",
          "拿到第二个候选的正常内容")
    app.state.usage_buffer.flush()
    row6 = last_usage(app)
    check(row6.get("attempt_count") >= 2,
          f"非流式 attempt_count>=2（实际 {row6.get('attempt_count')}）")

    # ---------- 8. 全失败时才保留完整尝试链（error_only 下） ----------
    print("\n[8] 全部候选都错误包 → 503 且尝试链完整")
    st, raw = stream_once(client, headers, BAD_MODEL)
    check(st == 503, f"返回 503（实际 {st}）")
    app.state.usage_buffer.flush()
    row7 = last_usage(app)
    check(row7.get("status") == "error", f"记为 error（实际 {row7.get('status')}）")
    det7 = detail_of(app, row7.get("id"))
    check(det7 is not None and (det7.get("detail") or {}).get("attempts"),
          "error_only 下失败请求的尝试链被保留")

    # ---------- 9. 聚合模型：首成员错误包 → 切到下一成员 ----------
    print("\n[9] 聚合模型 agg-dup（2 成员，首成员错误包）→ 自动切到第二成员")
    st, raw = stream_once(client, headers, "agg-dup")
    check(st == 200, f"聚合请求最终 200（实际 {st}）")
    check("t0" in raw and "t1" in raw, "拿到第二成员的正常正文")
    check("unapproved" not in raw, "错误包未透传给客户端")
    check(parse_usage(raw) is not None, "usage 正常透传")
    app.state.usage_buffer.flush()
    row8 = last_usage(app)
    check(row8.get("status") == "success", f"聚合走通后记为 success（实际 {row8.get('status')}）")
    check(row8.get("attempt_count") >= 2,
          f"聚合内发生了成员切换 attempt_count>=2（实际 {row8.get('attempt_count')}）")
    check(row8.get("upstream_id") == "src_good",
          f"最终命中第二成员 src_good（实际 {row8.get('upstream_id')}）")

    print("\n[9b] 聚合模型非流式同样切换")
    # CH-051：静态聚合改为权重轮询，连续请求会先落到第二成员；
    # 这里重置轮询状态，回到「首成员先试」以继续验证非流式的失败切换逻辑
    app.state.router_service.weighted.reset("agg-dup")
    r = client.post("/v1/chat/completions", headers=headers, json={
        "model": "agg-dup", "messages": [{"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"非流式聚合返回 200（实际 {r.status_code}）")
    app.state.usage_buffer.flush()
    row9 = last_usage(app)
    check(row9.get("attempt_count") >= 2,
          f"非流式聚合 attempt_count>=2（实际 {row9.get('attempt_count')}）")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

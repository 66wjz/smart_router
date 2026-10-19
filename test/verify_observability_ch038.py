"""CH-038 验证：请求详情可观测性 + 断连记录

用法：python test/verify_observability_ch038.py

覆盖：
    1. parse_cache_tokens 三种命名兼容
    2. 截断策略（头 3/4 + 尾 1/4 + 标注）
    3. 采集策略三档：off / error_only / all
    4. 报文脱敏（sk- 凭据）
    5. 断连记录 499（ASGI 中间件）
    6. 真实链路：REQUEST / FORWARDED / RESPONSE 三栏 + 尝试链
    7. 多候选失败重试 → attempt_count / attempts
    8. 详情接口 404 与 available=false
    9. 主表/详情表同步清理（无孤儿行）
    10. contextvar 并发隔离

不依赖外网；临时库，跑完即删。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


# ---------------------------------------------------------------- 单元

def test_cache_tokens() -> None:
    from app.core.usage import parse_cache_tokens

    print("\n[1] 缓存 token 三种命名兼容")
    check(parse_cache_tokens({"prompt_tokens_details": {"cached_tokens": 128}}) == (128, 0),
          "OpenAI 风格 prompt_tokens_details.cached_tokens")
    check(parse_cache_tokens({"cache_read_input_tokens": 256,
                              "cache_creation_input_tokens": 32}) == (256, 32),
          "Anthropic 风格 cache_read/write")
    check(parse_cache_tokens({"prompt_cache_hit_tokens": 512,
                              "prompt_cache_miss_tokens": 64}) == (512, 64),
          "中转站风格 prompt_cache_hit/miss")
    check(parse_cache_tokens({"prompt_tokens": 10}) == (0, 0), "无缓存字段 → (0, 0)")
    check(parse_cache_tokens(None) == (0, 0), "usage 为空 → (0, 0)")
    check(parse_cache_tokens({"prompt_tokens_details": {"cached_tokens": -5}}) == (0, 0),
          "负值被夹到 0")


def test_truncate() -> None:
    from app.core.usage import UsageBuffer

    print("\n[2] 报文截断：头 3/4 + 尾 1/4 + 标注")
    text = "A" * 300 + "B" * 300
    out = UsageBuffer._truncate(text, 200)
    check("…[truncated 400 bytes]…" in out, "含截断标注且字节数正确")
    check(out.startswith("A" * 150), "头部保留 3/4（150 字符）")
    check(out.endswith("B" * 50), "尾部保留 1/4（50 字符）")
    short = "x" * 50
    check(UsageBuffer._truncate(short, 100) == short, "未超限 → 原样")
    check(UsageBuffer._truncate(None, 100) is None, "None 原样返回")


def test_policy_and_redaction() -> None:
    import app.core.usage as usage_mod

    print("\n[3] 采集策略三档 + 脱敏")

    class Buf(usage_mod.UsageBuffer):
        def __init__(self, mode):
            super().__init__(retention_days=14, settings_getter=lambda: {
                "usage_detail_mode": mode, "usage_detail_max_bytes": 1024,
            })

    def reset_cv():
        usage_mod.current_request_body.set('{"model":"m","api_key":"sk-abcdef123456"}')
        usage_mod.current_forward_body.set('{"model":"up-model"}')
        usage_mod.current_response_body.set('{"error":{"message":"boom sk-zzzz9999yyyy"}}')
        usage_mod.current_request_headers.set({"user-agent": "pytest"})
        usage_mod.current_attempts.set([])

    # off
    reset_cv()
    buf = Buf("off")
    entry = {"status": "error"}
    buf.record(entry)
    check("detail" not in entry, "off：失败请求也不存详情")

    # error_only
    reset_cv()
    buf = Buf("error_only")
    entry_ok = {"status": "success"}
    buf.record(entry_ok)
    check("detail" not in entry_ok, "error_only：成功请求不存详情")

    reset_cv()
    entry_err = {"status": "error"}
    buf.record(entry_err)
    detail = entry_err.get("detail") or {}
    req_body = detail.get("request_body") or ""
    check(bool(detail), "error_only：失败请求存详情")
    check("sk-abcdef123456" not in req_body and "****" in req_body,
          f"请求体 sk- 凭据已脱敏（实际 {req_body[:60]}）")
    check("sk-zzzz9999yyyy" not in (detail.get("response_body") or ""), "响应体凭据已脱敏")
    check(json.loads(detail.get("request_headers") or "{}").get("user-agent") == "pytest",
          "请求头白名单字段保留")
    check(detail.get("attempts") == "[]", "attempts 空列表仍可序列化")

    # all
    reset_cv()
    buf_all = Buf("all")
    entry_all = {"status": "success"}
    buf_all.record(entry_all)
    check(bool(entry_all.get("detail")), "all：成功请求也存详情")


def test_disconnect_499() -> None:
    import asyncio

    import app.core.logging_setup as ls

    print("\n[4] 断连记录：未发响应 + http.disconnect → 499")

    captured: list[dict] = []
    original = ls._log_access

    def fake_log(scope, info, state, client, started, status, disconnected=False):
        captured.append({"status": status, "disconnected": disconnected})

    async def scenario(disconnect: bool, respond: bool) -> None:
        captured.clear()
        msgs = [{"type": "http.request",
                 "body": b'{"model":"m","stream":false,"messages":[]}',
                 "more_body": False}]
        if disconnect:
            msgs.append({"type": "http.disconnect"})

        async def receive():
            return msgs.pop(0) if msgs else {"type": "http.disconnect"}

        async def send(_msg):
            return None

        async def app(scope, receive, send):
            await receive()          # 缓存体回放
            if disconnect:
                await receive()      # 触发 http.disconnect
            if respond:
                await send({"type": "http.response.start", "status": 200,
                            "headers": []})

        mw = ls.RequestContextMiddleware(app)
        scope = {"type": "http", "path": "/v1/chat/completions", "method": "POST",
                 "state": {}, "client": ("127.0.0.1", 1234)}
        await mw(scope, receive, send)

    ls._log_access = fake_log
    try:
        asyncio.run(scenario(disconnect=True, respond=False))
        check(len(captured) == 1 and captured[0]["status"] == 499
              and captured[0]["disconnected"] is True,
              f"断开且未响应 → 记 499（实际 {captured}）")

        asyncio.run(scenario(disconnect=False, respond=True))
        check(len(captured) == 1 and captured[0]["status"] == 200,
              f"正常请求只记一次 200（实际 {captured}）")

        asyncio.run(scenario(disconnect=True, respond=True))
        check(all(c["status"] != 499 for c in captured),
              "已发响应后断开 → 不重复记 499")
    finally:
        ls._log_access = original


def test_contextvar_isolation() -> None:
    import asyncio

    import app.core.usage as usage_mod
    from app.upstream.openai_adapter import _note_attempt

    print("\n[5] contextvar 并发隔离")

    async def worker(i: int) -> list:
        usage_mod.current_attempts.set([])
        _note_attempt(f"u{i}", f"m{i}", 200, 10)
        await asyncio.sleep(0.01)
        _note_attempt(f"u{i}", f"m{i}", 503, 20)
        return usage_mod.current_attempts.get() or []

    async def run():
        return await asyncio.gather(*[worker(i) for i in range(8)])

    results = asyncio.run(run())
    ok = True
    for i, items in enumerate(results):
        if len(items) != 2 or any(a["upstream"] != f"u{i}" for a in items):
            ok = False
    check(ok, "8 个并发任务各自 2 条尝试，互不串味")


# ---------------------------------------------------------------- 集成

def _build_temp_db() -> str:
    import sqlite3

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch038")
    os.makedirs(tmpdir, exist_ok=True)
    db_path = os.path.join(tmpdir, "t.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["SMART_ROUTER_DB"] = db_path

    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    sql_root = os.path.join(ROOT, "sql")
    sql_files = [
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
    conn = sqlite3.connect(db_path)
    for rel in sql_files:
        path = os.path.join(sql_root, rel.replace("/", os.sep))
        with open(path, encoding="utf-8") as f:
            try:
                conn.executescript(f.read())
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
    conn.commit()
    conn.close()
    return db_path


def test_integration() -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from starlette.testclient import TestClient

    db_path = _build_temp_db()
    print(f"\n集成库: {db_path}")

    class BaseMock(BaseHTTPRequestHandler):
        fail_status = 0

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.fail_status:
                body = json.dumps({"error": {"message": f"mock {self.fail_status} boom"}}).encode()
                self.send_response(self.fail_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = json.dumps({
                "id": "x", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100,
                          "prompt_tokens_details": {"cached_tokens": 60},
                          "completion_tokens": 20, "total_tokens": 120},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    good = HTTPServer(("127.0.0.1", 0), type("Good", (BaseMock,), {"fail_status": 0}))
    bad = HTTPServer(("127.0.0.1", 0), type("Bad", (BaseMock,), {"fail_status": 400}))
    for s in (good, bad):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    time.sleep(0.3)

    from app.core.config import config
    from app.main import app
    from app.repositories.api_key_repo import ApiKeyRepository

    config.add_upstream({
        "id": "good", "name": "good", "base_url": f"http://127.0.0.1:{good.server_address[1]}",
        "api_key": "sk-mock", "format": "openai", "groups": ["free"],
        "probe_enabled": False, "models": [{"name": "good-model", "enabled": True}],
    })
    config.add_upstream({
        "id": "bad", "name": "bad", "base_url": f"http://127.0.0.1:{bad.server_address[1]}",
        "api_key": "sk-mock", "format": "openai", "groups": ["free"],
        "probe_enabled": False, "models": [{"name": "bad-model", "enabled": True}],
    })
    config.save_aggregation("ch038-agg", {
        "kind": "static",
        "members": [{"upstream": "bad", "model": "bad-model", "weight": 1},
                    {"upstream": "good", "model": "good-model", "weight": 1}],
        "rule_bindings": None, "groups": [], "enabled": True, "probe_enabled": False,
        "template_id": None, "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "",
    })
    ApiKeyRepository().create("t", "sk-test-ch038", '["free"]', True)
    config.reload()

    # 管理端 token（直接签一个，避免依赖默认密码）
    from app.core.security import create_jwt
    admin = {"Authorization": f"Bearer {create_jwt({'sub': 'admin', 'exp': int(time.time()) + 3600})}"}
    client = TestClient(app)
    api = {"Authorization": "Bearer sk-test-ch038"}

    def set_mode(mode: str) -> None:
        config.set_setting("usage_detail_mode", mode)

    def flush() -> None:
        app.state.usage_buffer.flush()

    def last_log_id() -> int:
        from app.repositories.usage_repo import UsageRepository
        rows = UsageRepository().query("SELECT id FROM log_usage ORDER BY id DESC LIMIT 1")
        return rows[0]["id"] if rows else 0

    set_mode("all")

    print("\n[6] 成功请求（mode=all）：三栏齐全 + 缓存 token")
    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "good-model",
        "messages": [{"role": "user", "content": "hello"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    flush()
    log_id = last_log_id()
    got = client.get(f"/admin/api/usage/logs/{log_id}", headers=admin)
    check(got.status_code == 200, "详情接口 200")
    data = got.json()
    detail = data.get("detail") or {}
    check(detail.get("available") is True, "detail.available=true")
    check("good-model" in (detail.get("request_body") or ""), "REQUEST 含原始请求")
    check("good-model" in (detail.get("forward_body") or ""), "FORWARDED 含实际转发体")
    check("ok" in (detail.get("response_body") or ""), "RESPONSE 含上游响应")
    check(detail.get("request_headers", {}).get("user-agent") is not None,
          "记录 user-agent")
    check(len(data.get("attempts") or []) == 1, "单次成功 → 1 条尝试")
    s = data.get("summary") or {}
    check(s.get("cache_read_tokens") == 60, f"cache_read_tokens=60（实际 {s.get('cache_read_tokens')}）")
    check(s.get("attempt_count") == 1, "attempt_count=1")

    print("\n[7] 失败后重试成功：尝试链 + attempt_count")
    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "ch038-agg",
        "messages": [{"role": "user", "content": "retry"}],
    })
    check(r.status_code == 200, f"聚合重试后 200（实际 {r.status_code}）")
    flush()
    data = client.get(f"/admin/api/usage/logs/{last_log_id()}", headers=admin).json()
    attempts = data.get("attempts") or []
    check(len(attempts) == 2, f"2 条尝试（实际 {len(attempts)}）")
    check(attempts[0].get("http_status") == 400, "第 1 条为 400 失败")
    check(attempts[1].get("http_status") == 200, "第 2 条为 200 成功")
    check((data.get("summary") or {}).get("attempt_count") == 2, "attempt_count=2")

    print("\n[8] 全失败：RESPONSE 保留上游错误体")
    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "bad-model",
        "messages": [{"role": "user", "content": "boom"}],
    })
    check(r.status_code >= 400, f"失败状态（实际 {r.status_code}）")
    flush()
    data = client.get(f"/admin/api/usage/logs/{last_log_id()}", headers=admin).json()
    check(data["summary"]["status"] != "success", "主表 status 非 success")
    body = (data.get("detail") or {}).get("response_body") or ""
    check("mock 400 boom" in body, "RESPONSE 保留上游错误信息")

    print("\n[9] error_only：成功不存详情、失败存详情")
    set_mode("error_only")
    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "good-model", "messages": [{"role": "user", "content": "no-detail"}],
    })
    flush()
    ok_id = last_log_id()
    ok_data = client.get(f"/admin/api/usage/logs/{ok_id}", headers=admin).json()
    check((ok_data.get("detail") or {}).get("available") is False, "成功请求 available=false")
    check("未采集" in ((ok_data.get("detail") or {}).get("reason") or "")
          or "早于" in ((ok_data.get("detail") or {}).get("reason") or ""),
          "给出不可用原因")

    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "bad-model", "messages": [{"role": "user", "content": "fail"}],
    })
    flush()
    err_data = client.get(f"/admin/api/usage/logs/{last_log_id()}", headers=admin).json()
    check((err_data.get("detail") or {}).get("available") is True, "失败请求仍有详情")

    print("\n[10] off：主表照常写入，详情全无")
    set_mode("off")
    r = client.post("/v1/chat/completions", headers=api, json={
        "model": "bad-model", "messages": [{"role": "user", "content": "off"}],
    })
    flush()
    off_id = last_log_id()
    off_data = client.get(f"/admin/api/usage/logs/{off_id}", headers=admin).json()
    check(off_data["summary"]["id"] == off_id, "主表写入正常")
    check((off_data.get("detail") or {}).get("available") is False, "off：无详情")

    print("\n[11] 详情接口边界")
    check(client.get("/admin/api/usage/logs/99999999", headers=admin).status_code == 404,
          "不存在的 id → 404")
    check(client.get(f"/admin/api/usage/logs/{off_id}").status_code == 401,
          "无 token → 401")

    print("\n[12] 设置接口读写")
    put = client.put("/admin/api/config/usage-detail", headers=admin,
                     json={"mode": "all", "max_bytes": 262144, "retention_days": 7})
    check(put.status_code == 200, f"PUT 200（实际 {put.status_code}）")
    cfg = client.get("/admin/api/config/usage-detail", headers=admin).json()
    check(cfg == {"mode": "all", "max_bytes": 262144, "retention_days": 7},
          f"回读一致（实际 {cfg}）")
    bad_mode = client.put("/admin/api/config/usage-detail", headers=admin,
                          json={"mode": "nope"})
    check(bad_mode.status_code == 422, "非法 mode → 422")
    bad_bytes = client.put("/admin/api/config/usage-detail", headers=admin,
                           json={"mode": "all", "max_bytes": 100})
    check(bad_bytes.status_code == 422, "max_bytes 过小 → 422")

    print("\n[13] 主表/详情表同步清理")
    from app.core.database import get_conn
    from app.repositories.usage_repo import UsageRepository

    repo = UsageRepository()
    old_ts = time.time() - 30 * 86400
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO log_usage (ts, model, status, http_status) VALUES (?, 'old', 'error', 500)",
        (old_ts,),
    )
    old_id = cur.lastrowid
    conn.execute(
        "INSERT INTO log_usage_detail (log_id, request_body) VALUES (?, 'old-body')",
        (old_id,),
    )
    conn.commit()

    before_main = repo.query_one("SELECT COUNT(*) AS c FROM log_usage")["c"]
    before_detail = repo.query_one("SELECT COUNT(*) AS c FROM log_usage_detail")["c"]
    repo.purge_older_than(7)
    after_main = repo.query_one("SELECT COUNT(*) AS c FROM log_usage")["c"]
    after_detail = repo.query_one("SELECT COUNT(*) AS c FROM log_usage_detail")["c"]
    check(after_main == before_main - 1, f"主表删除 1 条（{before_main} → {after_main}）")
    check(after_detail == before_detail - 1, f"详情表删除 1 条（{before_detail} → {after_detail}）")
    check(repo.query_one("SELECT COUNT(*) AS c FROM log_usage_detail WHERE log_id = ?",
                         (old_id,))["c"] == 0,
          "过期详情行已删（无孤儿）")
    orphans = repo.query_one(
        "SELECT COUNT(*) AS c FROM log_usage_detail d "
        "LEFT JOIN log_usage u ON u.id = d.log_id WHERE u.id IS NULL")["c"]
    check(orphans == 0, f"全库无孤儿详情行（{orphans}）")

    print("\n[14] 列表接口补字段（只增不改）")
    listing = client.get("/admin/api/usage/logs", headers=admin,
                         params={"range": "today", "size": 5}).json()
    item = (listing.get("items") or [{}])[0]
    for key in ("cache_read_tokens", "cache_write_tokens", "attempt_count",
                "prompt_tokens", "completion_tokens", "total_tokens",
                "duration_ms", "error_msg"):
        check(key in item, f"列表含字段 {key}")

    good.shutdown()
    bad.shutdown()


def main() -> int:
    test_cache_tokens()
    test_truncate()
    test_policy_and_redaction()
    test_disconnect_499()
    test_contextvar_isolation()
    try:
        test_integration()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check(False, f"集成测试异常: {e}")

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

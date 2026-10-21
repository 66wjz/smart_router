"""CH-041 验证：请求过滤引擎（Pre-flight Filter）

用法：python test/verify_filter_engine_ch041.py

覆盖：
    1. 引擎关闭（默认）→ 行为与改动前完全一致，零影响
    2. 聚合请求，首成员命中 → 静默切到第二成员，客户端 200
    3. 聚合请求，全部成员命中 → 503 + 列出规则名与被过滤的源
    4. 单模型直连命中 → 400 + 明确提示，不路由
    5. 单模型直连未命中 → 正常转发
    6. upstream_ids 限定作用域 → 只对指定源生效
    7. 规则禁用 → 不生效
    8. 未命中任何规则 → 零影响
    9. 试跑端点 → 正确返回命中结果
    10. 过滤后记账 → error_msg 带【已过滤】前缀，且尝试链记录「未发送」

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

DSH_LINE = "You are an AI agent powered by DeepSeek Harness."
NORMAL_LINE = "You are a helpful assistant."
SHARED_MODEL = "shared-model"
# 显式 static 聚合（agg_unified 行）—— 只有这类才走「聚合门面」语义。
# 注意：shared-model 只是同名模型分布在两个源，auto_same_name_aggregate 默认关闭，
# 因此它走 direct 分支（用户明确请求了这个模型名），不能自动换源。
AGG_MODEL = "agg-shared"


class MockUpstream(BaseHTTPRequestHandler):
    """记录每次被调用的源，供断言「有没有真的发出去」"""

    hits: list[str] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        auth = self.headers.get("Authorization", "")
        stream = bool(payload.get("stream"))
        # 用 Key 区分来源
        src = "src_a" if "sk-mock-a" in auth else "src_b"
        MockUpstream.hits.append(src)

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(2):
                chunk = {"id": "x", "object": "chat.completion.chunk",
                         "choices": [{"index": 0, "delta": {"content": f"{src}-t{i}"},
                                      "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            usage = {"id": "x", "object": "chat.completion.chunk", "choices": [],
                     "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return

        body = json.dumps({
            "id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"hello-from-{src}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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
    conn.execute("DELETE FROM sys_setting WHERE key='usage_detail_mode'")
    conn.execute("INSERT INTO sys_setting(key,value) VALUES('usage_detail_mode','\"error_only\"')")
    conn.commit()
    conn.close()

    from app.core.config import config
    from app.main import app, health
    from app.repositories.aggregation_repo import AggregationRepository
    from app.repositories.api_key_repo import ApiKeyRepository

    config.add_upstream({
        "id": "src_a", "name": "src_a", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock-a", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": SHARED_MODEL, "enabled": True},
                   {"name": "only-a", "enabled": True}],
    })
    config.add_upstream({
        "id": "src_b", "name": "src_b", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock-b", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": SHARED_MODEL, "enabled": True}],
    })
    AggregationRepository().upsert("agg-shared", {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": "src_a", "model": SHARED_MODEL, "weight": 1},
            {"upstream": "src_b", "model": SHARED_MODEL, "weight": 1},
        ],
        "sort_mode": "stable", "remark": "CH-041 验证",
    })
    ApiKeyRepository().create("t", "sk-test-ch041", '["free"]', True)
    config.reload()
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def last_usage():
    from app.repositories.usage_repo import UsageRepository
    rows = UsageRepository().query(
        "SELECT id, status, http_status, upstream_id, attempt_count, error_msg "
        "FROM log_usage ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else {}


def detail_of(log_id):
    from app.repositories.usage_repo import UsageRepository
    return UsageRepository().get_detail(log_id)


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch041")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)

    from starlette.testclient import TestClient
    client = TestClient(app)
    headers = {"Authorization": "Bearer sk-test-ch041"}

    from app.core.config import config

    def ask(model, system_text, stream=False):
        body = {"model": model, "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": "hi"}]}
        if stream:
            body["stream"] = True
            with client.stream("POST", "/v1/chat/completions", headers=headers, json=body) as r:
                raw = b"".join(r.iter_bytes()).decode("utf-8", "ignore")
            return r.status_code, raw
        r = client.post("/v1/chat/completions", headers=headers, json=body)
        return r.status_code, r.text

    def dsh_rule(enabled=True, upstream_ids=None, action="skip"):
        return {
            "name": "DSH 身份声明", "enabled": enabled,
            "target": "system_first_line", "pattern": "powered by DeepSeek Harness",
            "upstream_ids": upstream_ids or [], "action": action, "remark": "",
        }

    # ---------- 1. 引擎关闭（默认）：零影响 ----------
    print("\n[1] 引擎关闭（默认）→ 行为与改动前完全一致")
    MockUpstream.hits.clear()
    st, _ = ask(AGG_MODEL, DSH_LINE)
    check(st == 200, f"聚合正常返回 200（实际 {st}）")
    check(len(MockUpstream.hits) == 1, f"确实发了 1 次上游请求（实际 {len(MockUpstream.hits)}）")
    app.state.usage_buffer.flush()
    row1 = last_usage()
    check(row1.get("status") == "success", f"记为 success（实际 {row1.get('status')}）")

    # ---------- 7. 规则禁用 → 不生效 ----------
    print("\n[7] 规则存在但 enabled=false → 不生效")
    rule_id = config.save_filter_rule(dsh_rule(enabled=False))
    config.set_filter_engine_enabled(True)   # 引擎开，但规则关
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, DSH_LINE)
    check(st == 200, f"仍正常返回 200（实际 {st}）")
    check(len(MockUpstream.hits) == 1, f"仍发了上游请求（实际 {len(MockUpstream.hits)}）")

    # ---------- 8. 未命中任何规则：零影响 ----------
    print("\n[8] 引擎开 + 规则开，但请求内容未命中 → 零影响")
    config.save_filter_rule(dsh_rule(enabled=True), rule_id)
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, NORMAL_LINE)
    check(st == 200, f"正常返回 200（实际 {st}）")
    check(len(MockUpstream.hits) == 1, f"正常发出 1 次（实际 {len(MockUpstream.hits)}）")

    # ---------- 2. 聚合首成员命中 → 静默切换 ----------
    print("\n[2] 聚合请求，首成员命中 → 静默切到第二成员（客户端无感）")
    # 规则只作用于 src_a，这样 src_b 能正常承接，才能验证「静默切换」
    config.save_filter_rule(dsh_rule(enabled=True, upstream_ids=["src_a"]), rule_id)
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, DSH_LINE)
    check(st == 200, f"客户端收到 200（实际 {st}）")
    check("error" not in raw.lower() or "src_b" in raw,
          "响应体无过滤提示（客户端无感）")
    check("src_b" in raw, f"内容来自未被过滤的 src_b（实际片段 {raw[:80]}）")
    check(MockUpstream.hits == ["src_b"],
          f"上游只收到 src_b 一次，src_a 未被请求（实际 {MockUpstream.hits}）")
    app.state.usage_buffer.flush()
    row2 = last_usage()
    check(row2.get("status") == "success", f"最终记为 success（实际 {row2.get('status')}）")
    check(row2.get("upstream_id") == "src_b",
          f"命中 src_b（实际 {row2.get('upstream_id')}）")
    # 成功请求在 error_only 策略下不写详情（CH-038 设计），尝试链改在
    # 全失败场景（用例 3）验证 —— 那里才会落详情。

    # ---------- 3. 聚合全部成员命中 → 503 ----------
    print("\n[3] 聚合请求，全部成员命中 → 503 + 列明规则与源")
    config.save_filter_rule({
        "name": "DSH 身份声明", "enabled": True, "target": "system_first_line",
        "pattern": "powered by DeepSeek Harness", "upstream_ids": [],
        "action": "skip", "remark": "",
    }, rule_id)
    # 让两个源都被过滤：规则不限定源，所以 src_a / src_b 都会命中
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, DSH_LINE)
    check(st == 503, f"返回 503（实际 {st}）")
    check(len(MockUpstream.hits) == 0,
          f"没有任何上游请求被发出（实际 {MockUpstream.hits}）")
    app.state.usage_buffer.flush()
    row3 = last_usage()
    check(row3.get("status") == "error", f"记为 error（实际 {row3.get('status')}）")
    check("【已过滤】" in (row3.get("error_msg") or ""),
          f"error_msg 带【已过滤】前缀（实际 {str(row3.get('error_msg'))[:60]}）")
    # 全失败时 error_only 会落详情，在此验证尝试链完整记录了「未发送」
    det3 = detail_of(row3.get("id"))
    atts3 = json.loads(((det3 or {}).get("detail") or {}).get("attempts") or "[]")
    filtered_notes = [a for a in atts3 if "被过滤规则拦截" in (a.get("error") or "")]
    check(len(filtered_notes) >= 2,
          f"尝试链记录了两个被过滤的候选（{len(filtered_notes)} 条）")
    check(all(a.get("http_status") is None for a in filtered_notes),
          "被过滤记录 http_status 全为 None（证明一个都没发出去）")

    # ---------- 4. 单模型直连命中 → 400 ----------
    print("\n[4] 单模型直连命中 → 400，且不路由到其他源")
    MockUpstream.hits.clear()
    st, raw = ask("only-a", DSH_LINE)
    check(st == 400, f"返回 400（实际 {st}）")
    check(len(MockUpstream.hits) == 0,
          f"没有回退到别的源（实际 {MockUpstream.hits}）")
    app.state.usage_buffer.flush()
    row4 = last_usage()
    check("【已过滤】" in (row4.get("error_msg") or ""),
          "直连命中同样记账为「已过滤」")

    # ---------- 5. 单模型直连未命中 → 正常 ----------
    print("\n[5] 单模型直连未命中 → 正常转发")
    MockUpstream.hits.clear()
    st, raw = ask("only-a", NORMAL_LINE)
    check(st == 200, f"正常返回 200（实际 {st}）")
    check(MockUpstream.hits == ["src_a"], f"命中 src_a（实际 {MockUpstream.hits}）")

    # ---------- 6. upstream_ids 限定作用域 ----------
    print("\n[6] upstream_ids 限定作用域 → 只对指定源生效")
    config.save_filter_rule({
        "name": "DSH 身份声明", "enabled": True, "target": "system_first_line",
        "pattern": "powered by DeepSeek Harness", "upstream_ids": ["src_a"],
        "action": "skip", "remark": "",
    }, rule_id)
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, DSH_LINE)
    check(st == 200, f"聚合返回 200（实际 {st}）")
    check(MockUpstream.hits == ["src_b"],
          f"src_a 被过滤、src_b 正常（实际 {MockUpstream.hits}）")
    # 反过来验证：限定到 src_b 时，src_a 应放行
    config.save_filter_rule({
        "name": "DSH 身份声明", "enabled": True, "target": "system_first_line",
        "pattern": "powered by DeepSeek Harness", "upstream_ids": ["src_b"],
        "action": "skip", "remark": "",
    }, rule_id)
    MockUpstream.hits.clear()
    st, raw = ask(AGG_MODEL, DSH_LINE)
    check(st == 200, f"聚合返回 200（实际 {st}）")
    check(MockUpstream.hits == ["src_a"],
          f"改为 src_a 放行、src_b 被过滤（实际 {MockUpstream.hits}）")

    # ---------- 9. 试跑端点（管理端，需 JWT） ----------
    print("\n[9] 试跑端点 → 正确返回命中结果")
    # 管理端接口走 JWT，不是客户端 API Key
    login = client.post("/admin/api/login",
                        json={"username": "admin", "password": "smart-router-2026"})
    if login.status_code != 200:
        # 生产默认密码可能已改；用配置里的账号
        from app.repositories.setting_repo import SettingRepository
        admin = SettingRepository().get("admin") or {}
        login = client.post("/admin/api/login", json={
            "username": admin.get("username", "admin"),
            "password": admin.get("password", ""),
        })
    token = login.json().get("token", "")
    jh = {"Authorization": f"Bearer {token}"}
    check(bool(token), "取得管理端 JWT")

    r = client.post("/admin/api/filter-rules/test", headers=jh, json={
        "body": {"model": SHARED_MODEL, "messages": [
            {"role": "system", "content": DSH_LINE},
            {"role": "user", "content": "hi"}]},
        "upstream_ids": ["src_a", "src_b"],
    })
    check(r.status_code == 200, f"试跑接口 200（实际 {r.status_code}）")
    data = r.json()
    check(data.get("matched") is True, "识别为命中")
    hit_srcs = {x.get("upstream") for x in data.get("results") or []}
    check(hit_srcs == {"src_b"},
          f"只有 src_b 命中（规则限定 src_b，实际 {hit_srcs}）")

    r2 = client.post("/admin/api/filter-rules/test", headers=jh, json={
        "body": {"model": SHARED_MODEL, "messages": [
            {"role": "system", "content": NORMAL_LINE},
            {"role": "user", "content": "hi"}]},
        "upstream_ids": ["src_a", "src_b"],
    })
    check(r2.status_code == 200, "未命中的试跑也 200")
    check(r2.json().get("matched") is False, "未命中时 matched=false")

    # ---------- 9b. 规则 CRUD ----------
    print("\n[9b] 管理端规则 CRUD")
    r = client.get("/admin/api/filter-rules", headers=jh)
    check(r.status_code == 200, f"列表 200（实际 {r.status_code}）")
    check("enabled" in r.json(), "返回含全局开关状态")
    check(len(r.json().get("rules") or []) >= 2, "含预置规则")

    r = client.post("/admin/api/filter-rules", headers=jh, json={
        "name": "CRUD 测试规则", "enabled": False,
        "target": "system_any", "pattern": "test-never-match-xyz",
        "upstream_ids": [], "action": "skip", "remark": "",
    })
    check(r.status_code == 200, f"新建 200（实际 {r.status_code}）")
    new_id = r.json().get("id")
    r = client.delete(f"/admin/api/filter-rules/{new_id}", headers=jh)
    check(r.status_code == 200, f"删除 200（实际 {r.status_code}）")

    # ---------- 10. 关闭引擎后立即恢复零影响 ----------
    print("\n[10] 关闭引擎 → 立即恢复为改动前行为")
    config.set_filter_engine_enabled(False)
    MockUpstream.hits.clear()
    st, _ = ask("only-a", DSH_LINE)
    check(st == 200, f"直连命中规则内容的请求也能正常走（实际 {st}）")
    check(MockUpstream.hits == ["src_a"], f"正常发出请求（实际 {MockUpstream.hits}）")

    # ---------- 预置规则检查 ----------
    print("\n[11] 增量 SQL 预置的两条规则存在且默认关闭")
    names = {r["name"]: r for r in config.list_filter_rules()}
    check("DSH 身份声明" in names, "预置「DSH 身份声明」")
    check("Claude Code 身份声明" in names, "预置「Claude Code 身份声明」")
    preset = names.get("Claude Code 身份声明") or {}
    check(preset.get("enabled") is False, "预置规则默认不启用（安全默认）")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

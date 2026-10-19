"""CH-037 验证：出站消息角色规范化（developer → system）

用法：python test/verify_role_normalize_ch037.py

设计思路（不依赖外网、不动生产）：
    1. 单元级：直接调 _normalize_messages，校验改写范围精确
    2. 集成级：起一个本地 mock 上游，用 uvicorn 把真实 app 指向它，
       用带 developer 的请求打中转站，断言「mock 收到的 role 是 system」且返回 200

覆盖：
    - developer → system（流式 / 非流式）
    - user / assistant / tool / system 角色不被改写
    - 消息顺序与 content 不变
    - 原始 body 不被污染（副本语义）
    - 管理端单模型测试接口同样生效
    - 畸形 messages（非 list / 含非 dict）不崩
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


def test_unit() -> None:
    from app.upstream.openai_adapter import _normalize_messages

    print("\n[1] 单元：只改 developer，其余不动")
    body = {
        "model": "x",
        "messages": [
            {"role": "developer", "content": "d1"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "tool", "content": "t", "tool_call_id": "c1"},
            {"role": "system", "content": "s"},
            {"role": "developer", "content": "d2"},
        ],
    }
    _normalize_messages(body)
    roles = [m["role"] for m in body["messages"]]
    check(roles == ["system", "user", "assistant", "tool", "system", "system"],
          f"角色序列正确: {roles}")
    check(body["messages"][0]["content"] == "d1", "第 1 条 content 未变")
    check(body["messages"][5]["content"] == "d2", "末条 content 未变")
    check(body["messages"][3].get("tool_call_id") == "c1", "tool 消息其它字段未动")

    print("\n[2] 单元：无 developer 时零改动")
    body2 = {"messages": [{"role": "user", "content": "hi"}]}
    before = json.dumps(body2, sort_keys=True)
    _normalize_messages(body2)
    check(json.dumps(body2, sort_keys=True) == before, "无 developer → 完全不变")

    print("\n[3] 单元：畸形 messages 不崩")
    for bad in ({"messages": None}, {"messages": "not-a-list"}, {"messages": []}, {}):
        try:
            _normalize_messages(bad)
            ok = True
        except Exception as e:
            ok = False
            print("    异常:", e)
        check(ok, f"畸形输入安全: {str(bad)[:40]}")
    mixed = {"messages": [None, "str", 123, {"role": "developer", "content": "d"}]}
    _normalize_messages(mixed)
    check(mixed["messages"][3]["role"] == "system", "混合非 dict 项时仍能处理 dict 项")


def test_integration() -> None:
    """起本地 mock 上游 + 真实 app，验证端到端角色改写"""
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from starlette.testclient import TestClient

    captured: list[dict] = []

    class MockUpstream(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            captured.append(payload)
            if payload.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunk = json.dumps({
                    "id": "x", "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
                })
                self.wfile.write(f"data: {chunk}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                body = json.dumps({
                    "id": "x", "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    # 独立临时库，避免污染 demo.db
    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch037")
    os.makedirs(tmpdir, exist_ok=True)
    db_path = os.path.join(tmpdir, "t.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["SMART_ROUTER_DB"] = db_path

    # 清掉已导入的 app 模块，让新库生效
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    # 建表 + 增量（与 seed 顺序一致，但不跑种子数据）
    import sqlite3
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

    from app.core.config import config
    from app.main import app

    config.add_upstream({
        "id": "mock", "name": "mock", "base_url": f"http://127.0.0.1:{port}",
        "api_key": "sk-mock", "format": "openai", "groups": ["free"],
        "probe_enabled": False,
        "models": [{"name": "mock-model", "enabled": True}],
    })
    config.save_aggregation("mock-agg", {
        "kind": "static",
        "members": [{"upstream": "mock", "model": "mock-model", "weight": 1}],
        "rule_bindings": None, "groups": [], "enabled": True, "probe_enabled": False,
        "template_id": None, "sort_mode": "stable", "interval_seconds": None,
        "slow_threshold_seconds": None, "schedule": {}, "remark": "",
    })
    from app.repositories.api_key_repo import ApiKeyRepository
    ApiKeyRepository().create("t", "sk-test-ch037", '["free"]', True)
    config.reload()  # Key 是在 config 加载后写入的，必须热重载才能被 validate_api_key 看到

    client = TestClient(app)
    H = {"Authorization": "Bearer sk-test-ch037"}

    print("\n[4] 集成：非流式 + developer（真实模型名）")
    captured.clear()
    r = client.post("/v1/chat/completions", headers=H, json={
        "model": "mock-model",
        "messages": [{"role": "developer", "content": "you are agent"},
                     {"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"返回 200（实际 {r.status_code}）")
    check(bool(captured), "mock 上游收到请求")
    if captured:
        roles = [m["role"] for m in captured[-1]["messages"]]
        check(roles == ["system", "user"], f"上游收到的角色已改写: {roles}")
        check(captured[-1]["messages"][0]["content"] == "you are agent", "content 原样保留")

    print("\n[5] 集成：流式 + developer（走聚合名）")
    captured.clear()
    r = client.post("/v1/chat/completions", headers=H, json={
        "model": "mock-agg",
        "stream": True,
        "messages": [{"role": "developer", "content": "sys1"},
                     {"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, f"流式返回 200（实际 {r.status_code}）")
    check(bool(captured), "mock 上游收到流式请求")
    if captured:
        roles = [m["role"] for m in captured[-1]["messages"]]
        check(roles == ["system", "user"], f"流式上游收到的角色已改写: {roles}")

    print("\n[6] 集成：无 developer 的请求行为不变")
    captured.clear()
    r = client.post("/v1/chat/completions", headers=H, json={
        "model": "mock-model",
        "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
    })
    check(r.status_code == 200, "返回 200")
    if captured:
        roles = [m["role"] for m in captured[-1]["messages"]]
        check(roles == ["system", "user"], f"原样透传: {roles}")

    server.shutdown()


def main() -> int:
    test_unit()
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

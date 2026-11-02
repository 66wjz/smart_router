"""CH-054 验证：向量模型（Embedding）接入

用法：python test/verify_embedding_ch054.py

覆盖：
    1. /v1/embeddings 单条 / 批量（512 维，usage.prompt_tokens）
    2. 请求体透传（input / dimensions 不被改写）
    3. 错误响应：缺 model / 缺 input / 空 input
    4. 类型隔离：聊天模型调向量 400；向量模型调聊天 400
    5. 失败切换：坏源 500 → 好源 200；仅坏源 503
    6. 别名：指向向量模型可用；指向聊天模型被拒
    7. 聚合名调向量 → 400
    8. /v1/models 输出 type / capability
    9. 管理端测试端点返回维度 512
    10. 用量表落 protocol=embedding 记录
    11. 探测计划不含向量模型

不依赖外网；临时库，跑完保留 .tmp_ch054（已 gitignore）。
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

failures: list[str] = []
MODEL = "bge-small-zh-v1.5"
CHAT_MODEL = "chat-model"
ALIAS = "alias-embed"
AGG = "embed-agg"

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
    "increment/13_增量_20261028_会话亲和.sql",
]


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


class MockEmbedding(BaseHTTPRequestHandler):
    """OpenAI 兼容嵌入上游；status_code 挂在 HTTPServer 实例上（可各实例不同）"""

    def do_GET(self):
        if self.path.endswith("/v1/models"):
            body = json.dumps({"object": "list", "data": [
                {"id": MODEL, "object": "model", "owned_by": "mock"},
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.server.last_payload = payload
        status = getattr(self.server, "status_code", 200)
        if status != 200:
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"mock upstream failure"}}')
            return

        raw_input = payload.get("input")
        items = raw_input if isinstance(raw_input, list) else [raw_input]
        data = [
            {"object": "embedding", "index": i, "embedding": [round(0.001 * (i + 1), 4)] * 512}
            for i, _ in enumerate(items)
        ]
        body = json.dumps({
            "object": "list",
            "data": data,
            "model": payload.get("model", MODEL),
            "usage": {"prompt_tokens": 13, "total_tokens": 13},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def build_app(db_path: str, good_port: int, bad_port: int):
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

    # 坏源先、好源后 → 验证候选顺序兜底
    config.add_upstream({
        "id": "embed-bad", "name": "embed-bad", "base_url": f"http://127.0.0.1:{bad_port}",
        "api_key": "sk-mock-bad", "format": "openai", "groups": ["free"],
        "probe_enabled": True,
        "models": [
            {"name": MODEL, "type": "embedding", "enabled": True},
            {"name": "bad-only", "type": "embedding", "enabled": True},
        ],
    })
    config.add_upstream({
        "id": "embed-good", "name": "embed-good", "base_url": f"http://127.0.0.1:{good_port}",
        "api_key": "sk-mock-good", "format": "openai", "groups": ["free"],
        "probe_enabled": True,
        "models": [
            {"name": MODEL, "type": "embedding", "enabled": True},
            {"name": CHAT_MODEL, "type": "chat", "enabled": True},
        ],
    })
    ApiKeyRepository().create("t", "sk-test-ch054", '["free"]', True)
    config.add_model_pointer(ALIAS, MODEL, "embed-good")
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [{"upstream": "embed-good", "model": MODEL, "weight": 1}],
        "sort_mode": "stable", "remark": "CH-054 向量聚合拒绝验证",
    })
    config.reload()
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    from app.main import health as _health
    _health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def main() -> int:
    good = HTTPServer(("127.0.0.1", 0), MockEmbedding)
    good.status_code = 200
    good_port = good.server_address[1]
    threading.Thread(target=good.serve_forever, daemon=True).start()

    bad = HTTPServer(("127.0.0.1", 0), MockEmbedding)
    bad.status_code = 500
    bad_port = bad.server_address[1]
    threading.Thread(target=bad.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch054")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), good_port, bad_port)

    from starlette.testclient import TestClient
    from app.core.config import config
    from app.core.database import get_conn
    from app.services.auth_service import make_admin_token

    client = TestClient(app, raise_server_exceptions=False)
    auth = {"Authorization": "Bearer sk-test-ch054"}
    admin = {"Authorization": f"Bearer {make_admin_token(config.admin_config)}"}

    print("\n[1] 单条 / 批量 / 请求体透传")
    r = client.post("/v1/embeddings", headers=auth, json={
        "model": MODEL, "input": "峨山县政务服务中心", "dimensions": 512, "custom_field": "keep-me",
    })
    check(r.status_code == 200, f"单条返回 200（实际 {r.status_code}）")
    if r.status_code != 200:
        print("   body:", r.text[:300])
    body = r.json() if r.status_code == 200 else {}
    check(len(body.get("data") or []) == 1, "data 返回 1 条")
    check(len((body.get("data") or [{}])[0].get("embedding") or []) == 512, "向量维度 512")
    check((body.get("usage") or {}).get("prompt_tokens") == 13, "usage.prompt_tokens 透传")
    check(body.get("model") == MODEL, "响应 model 为真实模型名")
    check(r.headers.get("x-served-by", "").startswith("embed-good/"),
          f"坏源失败后切到好源（X-Served-By={r.headers.get('x-served-by')}）")
    check(good.last_payload.get("dimensions") == 512, "dimensions 原样透传")
    check(good.last_payload.get("custom_field") == "keep-me", "未知字段原样透传")

    r = client.post("/v1/embeddings", headers=auth, json={"model": MODEL, "input": ["a", "b", "c"]})
    check(r.status_code == 200 and len(r.json().get("data") or []) == 3,
          f"批量 3 条返回 3 个向量（实际 {r.status_code}）")

    print("\n[2] 入站校验")
    for name, payload in [
        ("缺 model", {"input": "x"}),
        ("缺 input", {"model": MODEL}),
        ("空 input", {"model": MODEL, "input": ""}),
        ("空数组", {"model": MODEL, "input": []}),
    ]:
        rr = client.post("/v1/embeddings", headers=auth, json=payload)
        check(rr.status_code == 400, f"{name} → 400（实际 {rr.status_code}）")

    print("\n[3] 类型隔离")
    rr = client.post("/v1/embeddings", headers=auth, json={"model": CHAT_MODEL, "input": "x"})
    check(rr.status_code == 400, f"聊天模型调向量 → 400（实际 {rr.status_code}）")
    rr = client.post("/v1/chat/completions", headers=auth, json={
        "model": MODEL, "messages": [{"role": "user", "content": "hi"}],
    })
    check(rr.status_code == 400, f"向量模型调聊天 → 400（实际 {rr.status_code}）")
    if rr.status_code == 400:
        check("向量模型" in rr.text, f"聊天错误提示含「向量模型」（{rr.text[:120]}）")

    print("\n[4] 失败切换")
    rr = client.post("/v1/embeddings", headers=auth, json={"model": "bad-only", "input": "x"})
    check(rr.status_code == 503, f"只有坏源 → 503（实际 {rr.status_code}）")

    print("\n[5] 别名 / 聚合拒绝")
    rr = client.post("/v1/embeddings", headers=auth, json={"model": ALIAS, "input": "x"})
    check(rr.status_code == 200, f"别名指向向量模型 → 200（实际 {rr.status_code}）")
    if rr.status_code == 200:
        check(rr.headers.get("x-served-by", "").startswith("embed-good/"),
              f"别名命中目标源（X-Served-By={rr.headers.get('x-served-by')}）")
    rr = client.post("/v1/embeddings", headers=auth, json={"model": AGG, "input": "x"})
    check(rr.status_code == 400, f"聚合名调向量 → 400（实际 {rr.status_code}）")

    print("\n[6] /v1/models")
    rr = client.get("/v1/models", headers=auth)
    check(rr.status_code == 200, f"模型列表 200（实际 {rr.status_code}）")
    items = {m["id"]: m for m in rr.json().get("data", [])}
    check(items.get(MODEL, {}).get("type") == "embedding", "向量模型带 type=embedding")
    check(items.get(CHAT_MODEL, {}).get("type") == "chat", "聊天模型带 type=chat")
    check(items.get(ALIAS, {}).get("capability") == "embedding", "别名 capability=embedding")
    check(items.get(AGG, {}).get("capability") == "chat", "聚合 capability=chat")

    print("\n[7] 管理端测试端点")
    rr = client.post(f"/admin/api/upstreams/embed-good/test", headers=admin, json={"model": MODEL})
    check(rr.status_code == 200, f"测试端点 200（实际 {rr.status_code}）")
    if rr.status_code == 200:
        data = rr.json()
        check(data.get("ok") is True and data.get("dimension") == 512,
              f"返回 ok + dimension=512（实际 {data}）")

    print("\n[8] 用量记账")
    app.state.usage_buffer.flush()
    rows = get_conn().execute(
        "SELECT model, protocol, stream, prompt_tokens, completion_tokens, status "
        "FROM log_usage WHERE protocol='embedding' ORDER BY id DESC LIMIT 10"
    ).fetchall()
    success_rows = [r for r in rows if r["status"] == "success"]
    check(len(success_rows) >= 3, f"protocol=embedding 成功至少 3 条（实际 {len(success_rows)}）")
    check(all(r["stream"] == 0 for r in rows), "向量用量 stream=0")
    check(all(r["prompt_tokens"] == 13 for r in success_rows), "成功请求 prompt_tokens=13")
    check(all(r["completion_tokens"] == 0 for r in rows), "向量用量 completion_tokens=0")
    check(any(r["status"] == "error" for r in rows), "失败请求也记 error（503 可查）")

    print("\n[9] 探测计划隔离")
    plan = config.collect_probe_plan()
    check(not any(k.endswith(":" + MODEL) for k in plan),
          f"探测计划不含向量模型（计划 {sorted(plan.keys())}）")

    print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAIL"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

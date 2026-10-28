"""CH-051 验证：聚合加权分发 + 聚合测试端点

用法：python test/verify_aggregation_weight_ch051.py

覆盖：
    1. SWRR 单元：权重 2/1/1 跑 100 次 → 50/25/25
    2. SWRR 重归一：只剩 2/1 → 100 次 ≈ 67/33
    3. 路由层：静态聚合 resolve_candidates 100 次 → 首位分布 50/25/25
    4. 成员冷却后：剔除冷却成员，剩余按 2/1 重新分配；冷却成员仍在兜底链里
    5. 全部冷却：候选不丢、不抛异常（原顺序兜底）
    6. 聚合测试端点：成员逐个 3/3 通过、权重份额 0.5/0.25/0.25、走聚合命中成员
    7. 连续两次测试命中的成员不同（权重轮换生效）
    8. 测试请求不写用量（log_usage 行数不变）

不依赖外网；临时库，跑完即删。
"""

import json
import os
import shutil
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

failures: list[str] = []

AGG = "weight_demo"
UP_A, UP_B, UP_C = "星-A", "乙-B", "src-C"
MODEL_A, MODEL_B, MODEL_C = "m-a", "m-b", "m-c"


class MockUpstream(BaseHTTPRequestHandler):
    """按 Key 区分是哪个上游源，返回可识别的回复"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        auth = self.headers.get("Authorization", "")
        tag = "A" if "sk-w-a" in auth else "B" if "sk-w-b" in auth else "C"
        body = json.dumps({
            "id": "x", "object": "chat.completion",
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": f"reply-{tag}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
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
    conn.commit()
    conn.close()

    from app.core.config import config
    from app.main import app
    from app.repositories.aggregation_repo import AggregationRepository

    for uid, key, model in [(UP_A, "sk-w-a", MODEL_A), (UP_B, "sk-w-b", MODEL_B), (UP_C, "sk-w-c", MODEL_C)]:
        config.add_upstream({
            "id": uid, "name": uid, "base_url": f"http://127.0.0.1:{port}",
            "api_key": key, "format": "openai", "groups": ["free"],
            "probe_enabled": False,
            "models": [{"name": model, "enabled": True}],
        })
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": UP_A, "model": MODEL_A, "weight": 2},
            {"upstream": UP_B, "model": MODEL_B, "weight": 1},
            {"upstream": UP_C, "model": MODEL_C, "weight": 1},
        ],
        "sort_mode": "stable", "remark": "CH-051 权重验证",
    })
    config.reload()
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    from app.main import health as _health
    _health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def main() -> int:
    # ---------- 1. SWRR 单元 ----------
    print("\n[1] SWRR 单元：2/1/1 → 50/25/25")
    from app.core.weighted_rr import WeightedRoundRobin
    rr = WeightedRoundRobin()
    items = [("A", 2), ("B", 1), ("C", 1)]
    c = Counter(rr.pick("u", items) for _ in range(100))
    check(c["A"] == 50 and c["B"] == 25 and c["C"] == 25,
          f"100 次分布 A/B/C = {c['A']}/{c['B']}/{c['C']}")

    print("\n[2] SWRR 单元：只剩 2/1 → ≈67/33")
    rr2 = WeightedRoundRobin()
    c2 = Counter(rr2.pick("u2", [("A", 2), ("B", 1)]) for _ in range(100))
    check(66 <= c2["A"] <= 67 and c2["B"] == 100 - c2["A"],
          f"100 次分布 A/B = {c2['A']}/{c2['B']}")

    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch051")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)
    svc = app.state.router_service
    health = app.state.health
    body = {"model": AGG, "messages": [{"role": "user", "content": "hi"}]}

    # ---------- 3. 路由层 100 次 ----------
    print("\n[3] 路由层 resolve_candidates ×100")
    hits = Counter()
    mode = ""
    for _ in range(100):
        cands, mode = svc.resolve_candidates(AGG, dict(body), None)
        check_len = len(cands)
        if check_len != 3:
            check(False, f"候选数应为 3，实际 {check_len}")
            break
        hits[cands[0]["model"]] += 1
    check(hits[MODEL_A] == 50 and hits[MODEL_B] == 25 and hits[MODEL_C] == 25,
          f"首位分布 {MODEL_A}/{MODEL_B}/{MODEL_C} = {hits[MODEL_A]}/{hits[MODEL_B]}/{hits[MODEL_C]}")
    check(mode == "static_agg", f"路由模式 static_agg（实际 {mode}）")

    # ---------- 4. C 冷却 → 2/1 重新归一 ----------
    print("\n[4] C 进入冷却 → 剩余按 2/1 重新分配")
    health.cooldown_until[f"{UP_C}:{MODEL_C}"] = time.time() + 3600
    hits2 = Counter()
    tail_has_c = 0
    for _ in range(100):
        cands, _ = svc.resolve_candidates(AGG, dict(body), None)
        hits2[cands[0]["model"]] += 1
        if any(x["model"] == MODEL_C for x in cands):
            tail_has_c += 1
    check(66 <= hits2[MODEL_A] <= 67 and hits2[MODEL_B] == 100 - hits2[MODEL_A] and hits2[MODEL_C] == 0,
          f"首位分布 {MODEL_A}/{MODEL_B}/{MODEL_C} = {hits2[MODEL_A]}/{hits2[MODEL_B]}/{hits2[MODEL_C]}")
    check(tail_has_c == 100, "冷却成员仍保留在兜底链里")

    # ---------- 5. 全员冷却 → 原顺序兜底 ----------
    print("\n[5] 全员冷却 → 候选不丢")
    health.cooldown_until[f"{UP_A}:{MODEL_A}"] = time.time() + 3600
    health.cooldown_until[f"{UP_B}:{MODEL_B}"] = time.time() + 3600
    cands, _ = svc.resolve_candidates(AGG, dict(body), None)
    check(len(cands) == 3, f"候选数仍为 3（实际 {len(cands)}）")
    check(cands[0]["model"] == MODEL_A, f"退回原顺序，首位 {cands[0]['model']}")
    health.cooldown_until.clear()
    health.fails.clear()

    # ---------- 6. 测试端点 ----------
    print("\n[6] 聚合测试端点：成员逐个 + 走聚合一次")
    from starlette.testclient import TestClient
    from app.services.auth_service import make_admin_token
    from app.core.config import config
    client = TestClient(app, raise_server_exceptions=False)
    admin = {"Authorization": f"Bearer {make_admin_token(config.admin_config)}"}
    from app.repositories.usage_repo import UsageRepository
    usage_before = UsageRepository().query("SELECT COUNT(*) AS n FROM log_usage")[0]["n"]

    r = client.post(f"/admin/api/aggregations/test?name={AGG}",
                    headers=admin, json={"prompt": "只回复ok", "include_aggregate": True})
    check(r.status_code == 200, f"HTTP 200（实际 {r.status_code}）")
    data = r.json()
    check(data["summary"] == {"total": 3, "ok": 3, "fail": 0, "skipped": 0},
          f"成员全部通过（{data['summary']}）")
    shares = {m["model"]: m["share"] for m in data["members"]}
    check(shares[MODEL_A] == 0.5 and shares[MODEL_B] == 0.25 and shares[MODEL_C] == 0.25,
          f"权重份额 {shares}")
    check(all("reply-" in (m.get("content") or "") for m in data["members"]), "每个成员都返回了内容")
    agg = data["aggregate"]
    check(agg and agg["ok"], f"走聚合成功（{agg and agg.get('error')}）")
    served1 = agg["served"]["model"] if agg and agg["served"] else None
    check(served1 in (MODEL_A, MODEL_B, MODEL_C), f"命中成员 {served1}")
    check(len(agg["tried"]) == 1, f"首次尝试即成功（尝试 {len(agg['tried'])} 次）")

    # ---------- 7. 连续两次命中不同成员 ----------
    print("\n[7] 连续两次测试 → 命中不同成员（权重轮换）")
    r2 = client.post(f"/admin/api/aggregations/test?name={AGG}",
                     headers=admin, json={"prompt": "只回复ok", "include_aggregate": True})
    served2 = r2.json()["aggregate"]["served"]["model"]
    check(served2 != served1, f"两次命中 {served1} → {served2}")

    # ---------- 8. 测试不写用量 ----------
    print("\n[8] 测试请求不写用量")
    app.state.usage_buffer.flush()
    usage_after = UsageRepository().query("SELECT COUNT(*) AS n FROM log_usage")[0]["n"]
    check(usage_after == usage_before, f"log_usage 行数不变（{usage_before} → {usage_after}）")

    # ---------- 9. 关闭的聚合拒绝测试 ----------
    print("\n[9] 不存在的聚合")
    r3 = client.post("/admin/api/aggregations/test?name=not-exist", headers=admin, json={})
    check(r3.status_code == 404, f"不存在的聚合 404（实际 {r3.status_code}）")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

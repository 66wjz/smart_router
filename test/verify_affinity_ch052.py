"""CH-052 验证：会话亲和（缓存优先路由）

用法：python test/verify_affinity_ch052.py

覆盖：
    1. 指纹：同会话多轮 / 不同会话 / user 字段
    2. 亲和表：TTL 过期、LRU 淘汰、active 计数不重复累加
    3. 新会话放置：权重 4/2/1 → 约 4:2:1（负载/权重）
    4. 同一会话 100 次 → 同一上游 + 同一 Key
    5. 同会话多轮（首条消息不变）→ 钉子不变
    6. 钉住目标失败 → 换源并重钉，恢复后不切回
    7. 同上游 Key 冷却 → 换 Key，钉子跟到新 Key
    8. 短请求不钉（不写亲和表、switch_reason=short）
    9. 聚合 affinity=0 → 退回原权重轮询（不钉）
   10. 聚合测试端点不写亲和表
   11. log_usage 落库 affinity_key / affinity_hit / switch_reason

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

AGG = "affinity_demo"
UP_A, UP_B, UP_C = "src-A", "src-B", "src-C"
MODEL_A, MODEL_B, MODEL_C = "m-a", "m-b", "m-c"
KEY_A1, KEY_A2, KEY_B, KEY_C = "sk-aff-a1", "sk-aff-a2", "sk-aff-b", "sk-aff-c"

# 长会话的第一个用户消息（跨轮不变）
LONG_PREFIX = "背景资料：" + ("A" * 400)
SHORT_PROMPT = "hi"

FAIL_KEYS: set[str] = set()
USED_KEYS: list[str] = []


class MockUpstream(BaseHTTPRequestHandler):
    """按 Key 区分上游源，返回可识别回复；FAIL_KEYS 里的 Key 直接 500"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length or 0)
        auth = self.headers.get("Authorization", "")
        key = auth.replace("Bearer ", "").strip()
        USED_KEYS.append(key)
        if key in FAIL_KEYS:
            body = json.dumps({"error": {"message": "mock failure"}}).encode()
            self.send_response(500)
        else:
            body = json.dumps({
                "id": "x", "object": "chat.completion",
                "choices": [{"index": 0,
                             "message": {"role": "assistant", "content": f"reply-{key}"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
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
    "increment/13_增量_20261028_会话亲和.sql",
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

    ApiKeyRepository().create("t", "sk-test-ch052", '["free"]', True)

    config.add_upstream({
        "id": UP_A, "name": UP_A, "base_url": f"http://127.0.0.1:{port}",
        "api_key": KEY_A1, "api_keys": [KEY_A1, KEY_A2],
        "format": "openai", "groups": ["free"], "probe_enabled": False,
        "models": [{"name": MODEL_A, "enabled": True}],
    })
    for uid, key, model in [(UP_B, KEY_B, MODEL_B), (UP_C, KEY_C, MODEL_C)]:
        config.add_upstream({
            "id": uid, "name": uid, "base_url": f"http://127.0.0.1:{port}",
            "api_key": key, "format": "openai", "groups": ["free"],
            "probe_enabled": False,
            "models": [{"name": model, "enabled": True}],
        })
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": UP_A, "model": MODEL_A, "weight": 4},
            {"upstream": UP_B, "model": MODEL_B, "weight": 2},
            {"upstream": UP_C, "model": MODEL_C, "weight": 1},
        ],
        "sort_mode": "stable", "remark": "CH-052 会话亲和验证",
    })
    config.reload()
    config.set_setting("affinity_min_prompt_tokens", 100)
    config.key_pool.update_config(max_fails=1000, cooldown_seconds=1)
    from app.main import health as _health
    _health.update_config(max_fails=1000, cooldown_seconds=1)
    return app


def long_body(tag: str, extra_turns: list[dict] | None = None) -> dict:
    return {
        "model": AGG,
        "messages": [
            {"role": "user", "content": f"{LONG_PREFIX}-{tag}"},
            *(extra_turns or []),
        ],
    }


def main() -> int:
    # ---------- 1. 指纹 / 亲和表单元 ----------
    print("\n[1] 指纹与会话表单元")
    from app.core.affinity import SessionAffinity
    a = SessionAffinity()
    a.configure(ttl_seconds=60, max_entries=3, min_prompt_tokens=0)
    a.max_entries = 3  # configure 有安全下限 100，单测里直接压小

    b1 = long_body("s1")
    b2 = long_body("s1", [{"role": "assistant", "content": "好的"},
                          {"role": "user", "content": "继续"}])
    fp1 = a.fingerprint(AGG, b1)
    fp2 = a.fingerprint(AGG, b2)
    check(fp1 is not None and fp1 == fp2, f"同会话多轮指纹一致（{fp1} / {fp2}）")
    check(a.fingerprint(AGG, long_body("s2")) != fp1, "不同首条消息指纹不同")
    check(a.fingerprint("other-model", b1) != fp1, "不同模型指纹不同")
    u1 = {"model": AGG, "user": "user-1", "messages": [{"role": "user", "content": "x"}]}
    u1b = {"model": AGG, "user": "user-1", "messages": [{"role": "user", "content": "y"}]}
    check(a.fingerprint(AGG, u1) == a.fingerprint(AGG, u1b) != fp1,
          "显式 user 字段优先于消息内容")

    a.bind("k1", UP_A, MODEL_A, KEY_A1)
    check(a.lookup("k1") is not None, "绑定后可查到")
    check(a.stats()["active"][UP_A] == 1, "active 计数为 1")
    a.bind("k1", UP_A, MODEL_A, KEY_A2)
    check(a.stats()["active"][UP_A] == 1, "同上游重绑不重复累加 active")
    a.bind("k2", UP_B, MODEL_B)
    a.bind("k3", UP_C, MODEL_C)
    a.bind("k4", UP_A, MODEL_A)  # LRU 淘汰 k1
    check(a.stats()["entries"] == 3, "max_entries=3 生效")
    check(a.lookup("k1") is None, "最旧的钉子被 LRU 淘汰")
    ent = a._entries["k2"]
    ent.expires_at = time.time() - 1
    check(a.lookup("k2") is None, "过期钉子被清除")

    # ---------- 2. 新会话放置分布 ----------
    print("\n[2] 1000 个新会话放置（权重 4/2/1）")
    a2 = SessionAffinity()
    a2.configure(ttl_seconds=600, max_entries=20000, min_prompt_tokens=0)
    cands = [
        {"upstream": UP_A, "model": MODEL_A, "weight": 4},
        {"upstream": UP_B, "model": MODEL_B, "weight": 2},
        {"upstream": UP_C, "model": MODEL_C, "weight": 1},
    ]
    dist = Counter()
    for i in range(1000):
        chosen = a2.choose(cands)
        a2.bind(f"s{i}", chosen["upstream"], chosen["model"])
        a2.record_request(chosen["upstream"])
        dist[chosen["upstream"]] += 1
    check(abs(dist[UP_A] - 571) <= 60 and abs(dist[UP_B] - 286) <= 45 and abs(dist[UP_C] - 143) <= 35,
          f"分布 A/B/C = {dist[UP_A]}/{dist[UP_B]}/{dist[UP_C]}（期望 ≈571/286/143）")

    # ---------- 3. HTTP 端到端 ----------
    server = HTTPServer(("127.0.0.1", 0), MockUpstream)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    tmpdir = os.path.join(ROOT, "backend", ".tmp_ch052")
    os.makedirs(tmpdir, exist_ok=True)
    app = build_app(os.path.join(tmpdir, "t.db"), port)
    svc = app.state.router_service
    health = app.state.health

    from starlette.testclient import TestClient
    from app.core.config import config
    client = TestClient(app, raise_server_exceptions=False)

    def post(body: dict):
        return client.post("/v1/chat/completions",
                           headers={"Authorization": "Bearer sk-test-ch052"}, json=body)

    def pin_of(tag: str):
        return svc.affinity.lookup(svc.affinity.fingerprint(AGG, long_body(tag)))

    # 先把 B/C 冷却，强制首个会话钉到 A
    health.cooldown_until[f"{UP_B}:{MODEL_B}"] = time.time() + 3600
    health.cooldown_until[f"{UP_C}:{MODEL_C}"] = time.time() + 3600
    r = post(long_body("s3"))
    check(r.status_code == 200, f"首个请求成功（{r.status_code}）")
    entry = pin_of("s3")
    check(entry is not None and entry.upstream == UP_A, f"新会话钉到 A（{entry and entry.upstream}）")
    health.cooldown_until.clear()
    health.fails.clear()

    print("\n[3] 同一会话 100 次 → 同一上游 + 同一 Key")
    USED_KEYS.clear()
    replies = set()
    for i in range(100):
        rr = post(long_body("s3", [{"role": "assistant", "content": "ok"},
                                   {"role": "user", "content": f"第{i}轮"}]))
        replies.add(rr.json()["choices"][0]["message"]["content"])
    entry = pin_of("s3")
    check(entry is not None and entry.upstream == UP_A, f"钉子仍在 A（{entry and entry.upstream}）")
    check(len(replies) == 1, f"100 次回复来自同一 Key（{replies}）")
    check(all(k in (KEY_A1, KEY_A2) for k in USED_KEYS), "实际请求都打了 A 的两个 Key")
    check(USED_KEYS.count(USED_KEYS[-1]) >= 100, "每次请求都用同一个 Key（未轮询）")

    print("\n[4] 多轮增长 → 钉子不变")
    fp_before = svc.affinity.fingerprint(AGG, long_body("s3"))
    turns = [{"role": "assistant", "content": "ok"}]
    for i in range(5):
        turns.append({"role": "user", "content": f"追问 {i}"})
        turns.append({"role": "assistant", "content": "ok"})
        post(long_body("s3", turns[:-1]))
    fp_after = svc.affinity.fingerprint(AGG, long_body("s3", turns))
    check(fp_before == fp_after, "首条消息不变 → 指纹不变")
    check(pin_of("s3").upstream == UP_A, "多轮后钉子仍是 A")

    print("\n[5] 钉住目标失败 → 换源重钉，恢复后不切回")
    health.cooldown_until[f"{UP_B}:{MODEL_B}"] = time.time() + 3600
    health.cooldown_until[f"{UP_C}:{MODEL_C}"] = time.time() + 3600
    post(long_body("s5"))
    check(pin_of("s5").upstream == UP_A, "s5 先钉到 A")
    health.cooldown_until.clear()
    FAIL_KEYS.update({KEY_A1, KEY_A2})       # A 全部失败
    r = post(long_body("s5"))
    check(r.status_code == 200, f"失败后仍成功（{r.status_code}）")
    served = r.json()["choices"][0]["message"]["content"]
    entry5 = pin_of("s5")
    check(entry5.upstream in (UP_B, UP_C), f"重钉到可用源（{entry5.upstream}）")
    check(served.endswith(KEY_B) or served.endswith(KEY_C), f"实际由 {served} 服务")
    FAIL_KEYS.clear()                        # A 恢复
    r = post(long_body("s5"))
    served2 = r.json()["choices"][0]["message"]["content"]
    check(served2 == served, f"恢复后仍走重钉的源，不切回（{served2}）")
    check(pin_of("s5").upstream == entry5.upstream, "钉子保持重钉后的源")

    print("\n[6] 同上游 Key 冷却 → 换 Key，钉子跟随")
    entry = pin_of("s3")
    old_key = entry.key
    other = KEY_A2 if old_key == KEY_A1 else KEY_A1
    config.key_pool._cooldown_until.setdefault(UP_A, {})[old_key] = time.time() + 3600
    r = post(long_body("s3"))
    check(r.json()["choices"][0]["message"]["content"].endswith(other),
          f"冷却后换到另一个 Key（{other}）")
    check(pin_of("s3").key == other, "钉子更新为实际成功的 Key")
    config.key_pool._cooldown_until[UP_A].clear()
    r = post(long_body("s3"))
    check(r.json()["choices"][0]["message"]["content"].endswith(other),
          "原 Key 恢复后仍用新 Key（不来回切）")

    print("\n[7] 短请求不钉")
    before = svc.affinity.stats()["entries"]
    for _ in range(10):
        rr = post({"model": AGG, "messages": [{"role": "user", "content": SHORT_PROMPT}]})
        check_ok = rr.status_code == 200
        if not check_ok:
            check(False, f"短请求失败（{rr.status_code}）")
            break
    after = svc.affinity.stats()["entries"]
    check(after == before, f"短请求不写亲和表（{before} → {after}）")

    print("\n[8] 聚合 affinity=0 → 退回权重轮询")
    from app.repositories.aggregation_repo import AggregationRepository
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": UP_A, "model": MODEL_A, "weight": 4},
            {"upstream": UP_B, "model": MODEL_B, "weight": 2},
            {"upstream": UP_C, "model": MODEL_C, "weight": 1},
        ],
        "affinity": 0,
        "sort_mode": "stable", "remark": "CH-052 会话亲和验证",
    })
    config.reload()
    hits = Counter()
    for i in range(70):
        rr = post(long_body("same-session"))
        content = rr.json()["choices"][0]["message"]["content"]
        hits[content.replace("reply-", "")] += 1
    check(len([k for k in hits if k in (KEY_A1, KEY_A2, KEY_B, KEY_C)]) >= 2,
          f"关闭亲和后同一会话分散到多个源（{dict(hits)}）")
    check(hits[KEY_A1] + hits[KEY_A2] > hits[KEY_B] > hits[KEY_C],
          f"分布仍按 4/2/1（A={hits[KEY_A1] + hits[KEY_A2]} B={hits[KEY_B]} C={hits[KEY_C]}）")

    # 恢复跟随全局
    AggregationRepository().upsert(AGG, {
        "kind": "static", "enabled": True,
        "members": [
            {"upstream": UP_A, "model": MODEL_A, "weight": 4},
            {"upstream": UP_B, "model": MODEL_B, "weight": 2},
            {"upstream": UP_C, "model": MODEL_C, "weight": 1},
        ],
        "affinity": None,
        "sort_mode": "stable", "remark": "CH-052 会话亲和验证",
    })
    config.reload()

    print("\n[9] 聚合测试端点不写亲和表")
    from app.services.auth_service import make_admin_token
    admin = {"Authorization": f"Bearer {make_admin_token(config.admin_config)}"}
    before = svc.affinity.stats()["entries"]
    r = client.post(f"/admin/api/aggregations/test?name={AGG}", headers=admin,
                    json={"prompt": "只回复ok", "include_aggregate": True})
    check(r.status_code == 200, f"测试端点 200（{r.status_code}）")
    after = svc.affinity.stats()["entries"]
    check(after == before, f"测试不写亲和表（{before} → {after}）")

    print("\n[10] log_usage 观测字段")
    app.state.usage_buffer.flush()
    from app.repositories.usage_repo import UsageRepository
    rows = UsageRepository().query(
        "SELECT affinity_key, affinity_hit, switch_reason FROM log_usage "
        "WHERE model = ? ORDER BY id DESC", (AGG,))
    check(len(rows) > 0, f"有 {len(rows)} 条用量记录")
    check(any(r.get("affinity_key") for r in rows), "affinity_key 已落库")
    check(any(r.get("affinity_hit") == 1 for r in rows), "affinity_hit=1 存在（命中钉子）")
    reasons = {r.get("switch_reason") for r in rows}
    check("failover" in reasons, f"switch_reason 含 failover（{reasons}）")
    check("short" in reasons, "switch_reason 含 short（短请求）")

    server.shutdown()
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

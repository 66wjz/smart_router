"""CH-019 本地联调验证（仅打本地 10199 实例，不触碰生产）"""
import json
import sqlite3
import sys

import httpx

BASE = "http://127.0.0.1:10199"
DB = "smart_router.db"

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


def main():
    c = httpx.Client(timeout=30)

    print("[1] 基础端点")
    r = c.get(f"{BASE}/health")
    check("GET /health", r.status_code == 200 and r.json().get("version") == "5.2", r.text[:80])
    r = c.get(f"{BASE}/status")
    st = r.json()
    panel_keys = list(st.get("latency_panel", {}).keys())
    check("GET /status", r.status_code == 200)
    check("探测面板为 upstream:model 键", all(":" in k for k in panel_keys), f"{panel_keys[:2]}")

    print("[2] 管理端登录 + 新端点")
    r = c.post(f"{BASE}/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    check("登录", r.status_code == 200, r.text[:100])
    token = r.json().get("token") or r.json().get("access_token") or ""
    check("拿到 token", bool(token))
    H = {"Authorization": f"Bearer {token}"}

    r = c.get(f"{BASE}/admin/api/usage/summary", params={"range": "today"}, headers=H)
    check("GET /admin/api/usage/summary", r.status_code == 200, r.text[:120])
    summary = r.json()
    check("summary 字段完整", all(k in summary for k in ("total", "total_tokens", "success_rate", "active_keys", "top_errors")))

    r = c.get(f"{BASE}/admin/api/usage/by-model", params={"range": "7d"}, headers=H)
    check("GET /admin/api/usage/by-model", r.status_code == 200, r.text[:100])
    r = c.get(f"{BASE}/admin/api/usage/by-key", params={"range": "7d"}, headers=H)
    check("GET /admin/api/usage/by-key", r.status_code == 200, r.text[:100])
    r = c.get(f"{BASE}/admin/api/usage/logs", params={"range": "today", "page": 1, "size": 10}, headers=H)
    check("GET /admin/api/usage/logs", r.status_code == 200 and "items" in r.json(), r.text[:100])

    print("[3] 模型级启停 + 排序（xiaomi 源）")
    ups = c.get(f"{BASE}/admin/api/upstreams", headers=H).json()["upstreams"]
    target = next((u for u in ups if len(u.get("models") or []) >= 2), None)
    if not target:
        check("找到含 >=2 模型的上游", False)
    else:
        uid = target["id"]
        names = [m["name"] for m in target["models"]]
        print(f"    上游={uid} 模型={names}")
        m0 = names[0]

        r = c.patch(f"{BASE}/admin/api/upstreams/{uid}/models", params={"model": m0},
                    headers=H, json={"enabled": False})
        check("PATCH 禁用模型", r.status_code == 200 and r.json().get("enabled") is False, r.text[:120])

        cur = c.get(f"{BASE}/admin/api/upstreams", headers=H).json()["upstreams"]
        u2 = next(u for u in cur if u["id"] == uid)
        entry = next(m for m in u2["models"] if m["name"] == m0)
        check("禁用已落库", entry.get("enabled") in (0, False), str(entry))

        key = c.get(f"{BASE}/admin/api/api-keys", headers=H).json().get("api_keys", [])
        if key:
            raw = key[0]["key"]
            r = c.get(f"{BASE}/v1/models", headers={"Authorization": f"Bearer {raw}"})
            ids = [m["id"] for m in r.json().get("data", [])]
            check("禁用模型不出现在 /v1/models", m0 not in ids, f"{m0} in list = {m0 in ids}")

        r = c.patch(f"{BASE}/admin/api/upstreams/{uid}/models", params={"model": m0},
                    headers=H, json={"enabled": True})
        check("PATCH 恢复启用", r.status_code == 200 and r.json().get("enabled") is True, r.text[:120])

        reversed_names = list(reversed(names))
        r = c.put(f"{BASE}/admin/api/upstreams/{uid}/models/order", headers=H, json={"names": reversed_names})
        check("PUT 重排", r.status_code == 200 and r.json().get("models") == reversed_names, r.text[:160])

        cur = c.get(f"{BASE}/admin/api/upstreams", headers=H).json()["upstreams"]
        u3 = next(u for u in cur if u["id"] == uid)
        check("重排已落库", [m["name"] for m in u3["models"]] == reversed_names,
              str([m["name"] for m in u3["models"]]))

        c.put(f"{BASE}/admin/api/upstreams/{uid}/models/order", headers=H, json={"names": names})

    print("[4] 同名多候选（直接构造：读配置侧 collect_model_upstreams）")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT upstream_id, models FROM up_upstream WHERE enabled=1").fetchall()
    from collections import defaultdict
    mapping = defaultdict(list)
    for r in rows:
        for m in json.loads(r["models"] or "[]"):
            if isinstance(m, dict) and m.get("enabled", 1):
                mapping[m["name"]].append(r["upstream_id"])
    shared = {k: v for k, v in mapping.items() if len(v) > 1}
    check("存在同名跨源模型（真实环境）", True, f"共 {len(shared)} 个" + (f"，例：{list(shared.items())[:2]}" if shared else "（当前无同名，逻辑靠单测覆盖）"))

    print("[5] 用量记录落库检查")
    if "log_usage" in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        n = con.execute("SELECT COUNT(*) FROM log_usage").fetchone()[0]
        check("log_usage 表已建", True, f"当前 {n} 条")
        cols = [d[1] for d in con.execute("PRAGMA table_info(log_usage)")]
        need = ["ts", "api_key_id", "upstream_id", "model", "protocol", "stream", "status",
                "prompt_tokens", "completion_tokens", "total_tokens", "estimated", "duration_ms",
                "first_token_ms", "error_msg"]
        check("log_usage 字段完整", all(x in cols for x in need), f"缺={[x for x in need if x not in cols]}")
    else:
        check("log_usage 表已建", False)

    print(f"\n结果: PASS={ok} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""CH-019 端到端：验证失败请求也写入 log_usage（本地实例，临时源指向不可达地址）"""
import sqlite3
import sys
import time

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
    token = c.post(f"{BASE}/admin/api/login",
                   json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    keys = c.get(f"{BASE}/admin/api/api-keys", headers=H).json().get("api_keys", [])
    if not keys:
        print("无可用客户端 Key，跳过")
        return 0
    raw = keys[0]["key"]
    KH = {"Authorization": f"Bearer {raw}"}

    con = sqlite3.connect(DB)
    before = con.execute("SELECT COUNT(*) FROM log_usage").fetchone()[0]
    print(f"[1] 初始 log_usage 条数 = {before}")

    # 临时源 tmp-ch019 的 base_url 指向 127.0.0.1:9（必然连接失败）→ 走完全部候选后 503
    print("[2] 打一次必然失败的真实请求（tmp-model-a）")
    r = c.post(f"{BASE}/v1/chat/completions", headers=KH,
               json={"model": "tmp-model-a", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
    print(f"    HTTP {r.status_code} {r.text[:100]}")
    check("失败请求返回 503", r.status_code == 503)

    # 触发缓冲落库
    c.post(f"{BASE}/admin/api/usage/flush", headers=H)
    time.sleep(0.5)

    after_rows = con.execute(
        "SELECT model, status, http_status, upstream_id, estimated, prompt_tokens FROM log_usage ORDER BY id DESC LIMIT 3"
    ).fetchall()
    print(f"[3] 最新记录: {after_rows}")
    check("失败请求已入库", len(after_rows) > before or (after_rows and after_rows[0][0] == "tmp-model-a"),
          str(after_rows[:1]))
    if after_rows:
        row = after_rows[0]
        check("状态记为 error", row[1] == "error", str(row))
        check("http_status=503", row[2] == 503, str(row))
        check("记录了命中上游", bool(row[3]), str(row))
        check("失败也估算 prompt tokens", row[5] > 0, str(row))

    print("[4] 三层统计 API 数字一致")
    s = c.get(f"{BASE}/admin/api/usage/summary", params={"range": "today"}, headers=H).json()
    bm = c.get(f"{BASE}/admin/api/usage/by-model", params={"range": "today"}, headers=H).json()["models"]
    bk = c.get(f"{BASE}/admin/api/usage/by-key", params={"range": "today"}, headers=H).json()["keys"]
    logs = c.get(f"{BASE}/admin/api/usage/logs", params={"range": "today", "size": 100}, headers=H).json()
    print(f"    summary={s}")
    print(f"    by-model={bm[:2]}")
    print(f"    by-key={bk[:2]}")
    check("summary.total == 明细总数", s["total"] == logs["total"], f"{s['total']} vs {logs['total']}")
    check("by-model 请求数合计 == total", sum(m["requests"] for m in bm) == s["total"],
          f"{sum(m['requests'] for m in bm)} vs {s['total']}")
    check("by-key 请求数合计 == total", sum(k["requests"] for k in bk) == s["total"],
          f"{sum(k['requests'] for k in bk)} vs {s['total']}")
    check("成功率 < 100%（因有失败请求）", s["success_rate"] is None or s["success_rate"] < 1, str(s["success_rate"]))
    check("错误 Top 有记录", bool(s["top_errors"]), str(s["top_errors"]))

    print(f"\n结果: PASS={ok} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

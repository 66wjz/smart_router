"""CH-021 用量按单元写入验证（写一条临时记录再删）"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.repositories.usage_repo import UsageRepository  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


repo = UsageRepository()
ts = time.time()
rows = [
    {"ts": ts, "api_key_id": 999999, "api_key_name": "__ch021__", "upstream_id": "__u1__",
     "upstream_name": "__上游1__", "model": "agg-name", "upstream_model": "real-model-a",
     "protocol": "chat", "stream": False, "status": "success", "http_status": 200,
     "prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300,
     "estimated": False, "duration_ms": 1200, "first_token_ms": None, "error_msg": None},
    {"ts": ts, "api_key_id": 999999, "api_key_name": "__ch021__", "upstream_id": "__u1__",
     "upstream_name": "__上游1__", "model": "agg-name", "upstream_model": "real-model-a",
     "protocol": "chat", "stream": True, "status": "success", "http_status": 200,
     "prompt_tokens": 50, "completion_tokens": 80, "total_tokens": 130,
     "estimated": False, "duration_ms": 800, "first_token_ms": 300, "error_msg": None},
    {"ts": ts, "api_key_id": 999999, "api_key_name": "__ch021__", "upstream_id": "__u2__",
     "upstream_name": "__上游2__", "model": "agg-name", "upstream_model": "real-model-b",
     "protocol": "chat", "stream": False, "status": "error", "http_status": 500,
     "prompt_tokens": 20, "completion_tokens": 0, "total_tokens": 20,
     "estimated": True, "duration_ms": 3000, "first_token_ms": None, "error_msg": "upstream 500"},
]

print("[1] 写入带 upstream_model 的记录")
n = repo.insert_many(rows)
check("insert_many 返回 3", n == 3, str(n))

print("\n[2] by-unit 聚合")
units = [u for u in repo.by_unit("30d") if u["upstream_id"] in ("__u1__", "__u2__")]
for u in units:
    print(f'    {u["upstream_id"]}/{u["upstream_model"]}: req={u["requests"]} err={u["error_count"]} tok={u["total_tokens"]}')
check("返回 2 个单元", len(units) == 2, str(len(units)))
u1 = next((u for u in units if u["upstream_id"] == "__u1__"), {})
u2 = next((u for u in units if u["upstream_id"] == "__u2__"), {})
check("u1 聚合到 real-model-a", u1.get("upstream_model") == "real-model-a", str(u1))
check("u1 请求数 2", u1.get("requests") == 2, str(u1.get("requests")))
check("u1 tokens 430", u1.get("total_tokens") == 430, str(u1.get("total_tokens")))
check("u1 request_models=1（请求名都是 agg-name）", u1.get("request_models") == 1, str(u1.get("request_models")))
check("u2 错误数 1", u2.get("error_count") == 1, str(u2.get("error_count")))

print("\n[3] 清理")
cur = repo.execute("DELETE FROM log_usage WHERE api_key_id = 999999")
check("临时记录已删除", cur.rowcount == 3, str(cur.rowcount))

print(f"\n===== 结果：{PASS} 通过 / {FAIL} 失败 =====")
sys.exit(0 if FAIL == 0 else 1)

"""CH-019 二期本地验证数据准备/清理：造两个上游各有同名模型（只动本地 DB）"""
import json
import sqlite3
import sys

DB = "smart_router.db"
A, B = "tmp-grp-a", "tmp-grp-b"
SHARED = "tmp/shared-model"


def _upsert(con, uid, name, models):
    con.execute(
        "INSERT OR REPLACE INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, groups, probe_enabled, models, smart_retry, enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (uid, name, "http://127.0.0.1:9/v1", "sk-tmp", "openai", "free",
         json.dumps(["free"]), 0, json.dumps(models, ensure_ascii=False), 0, 1),
    )


def setup():
    con = sqlite3.connect(DB)
    _upsert(con, A, "CH019 聚合源 A", [{"name": SHARED, "enabled": 1}, {"name": "only-a", "enabled": 1}])
    _upsert(con, B, "CH019 聚合源 B", [{"name": SHARED, "enabled": 1}])
    con.execute("DELETE FROM agg_model_group WHERE model = ?", (SHARED,))
    con.commit()
    print(f"setup ok: {A}, {B} 共享模型 {SHARED}")


def cleanup():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM up_upstream WHERE upstream_id IN (?,?)", (A, B))
    con.execute("DELETE FROM agg_model_group WHERE model = ?", (SHARED,))
    con.execute("DELETE FROM log_usage")
    con.commit()
    print("cleanup ok")


if __name__ == "__main__":
    (cleanup if len(sys.argv) > 1 and sys.argv[1] == "clean" else setup)()

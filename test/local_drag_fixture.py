"""复现拖拽 404：造两个含多模型的真实源（仅本地 DB）"""
import json
import sqlite3
import sys

DB = "smart_router.db"
SETS = [
    ("tmp-drag-a", "拖拽测试 A", ["drag-a1", "drag-a2", "drag-a3"]),
    ("tmp-drag-b", "拖拽测试 B", ["drag-b1", "drag-b2"]),
]


def setup():
    con = sqlite3.connect(DB)
    for uid, name, models in SETS:
        con.execute(
            "INSERT OR REPLACE INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, groups, probe_enabled, models, smart_retry, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (uid, name, "http://127.0.0.1:9/v1", "sk-tmp", "openai", "free",
             json.dumps(["free"]), 0,
             json.dumps([{"name": n, "enabled": 1} for n in models], ensure_ascii=False), 0, 1),
        )
    con.commit()
    print("setup ok")


def cleanup():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM up_upstream WHERE upstream_id LIKE 'tmp-drag-%'")
    con.execute("DELETE FROM agg_model_group")
    con.commit()
    print("cleanup ok")


if __name__ == "__main__":
    (cleanup if len(sys.argv) > 1 and sys.argv[1] == "clean" else setup)()

"""本地准备/清理：为 CH-019 联调造一个含 2 个模型的临时上游源（只动本地 DB）"""
import json
import sqlite3
import sys

DB = "smart_router.db"
UID = "tmp-ch019"


def setup():
    con = sqlite3.connect(DB)
    models = json.dumps([
        {"name": "tmp-model-a", "enabled": 1, "order": 0},
        {"name": "tmp-model-b", "enabled": 1, "order": 1},
    ], ensure_ascii=False)
    con.execute(
        "INSERT OR REPLACE INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, groups, probe_enabled, models, smart_retry, enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (UID, "CH019 联调临时源", "http://127.0.0.1:9/v1", "sk-tmp", "openai", "free",
         json.dumps(["free"]), 0, models, 0, 1),
    )
    con.commit()
    print("setup ok")


def cleanup():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM up_upstream WHERE upstream_id=?", (UID,))
    con.commit()
    print("cleanup ok")


if __name__ == "__main__":
    (cleanup if len(sys.argv) > 1 and sys.argv[1] == "clean" else setup)()

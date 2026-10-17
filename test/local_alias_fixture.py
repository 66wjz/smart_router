"""CH-019 异名聚合同步验证：造 3 个源（buddy/loomy/trae）含异名 deepseek-v4.1-flash（仅本地 DB）"""
import json
import sqlite3
import sys

DB = "smart_router.db"
SETS = [
    ("tmp-buddy", "Buddy 池", ["buddy/deepseek-v4.1-flash", "buddy/glm-5.3"]),
    ("tmp-loomy", "Loomy 池", ["loomy/DeepSeek-V4.1-Flash"]),
    ("tmp-trae", "Trae 池", ["trae/deepseek-v4.1-flash", "trae/glm-5.3-flash"]),
]


def setup():
    con = sqlite3.connect(DB)
    for uid, name, models in SETS:
        con.execute(
            "INSERT OR REPLACE INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, groups, probe_enabled, models, smart_retry, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (uid, name, "http://127.0.0.1:9/v1", "sk-tmp", "openai", "free",
             json.dumps(["free"]), 0, json.dumps([{"name": n, "enabled": 1} for n in models], ensure_ascii=False), 0, 1),
        )
    con.execute("DELETE FROM agg_model_group WHERE model LIKE 'deepseek%'")
    con.commit()
    print("setup ok")


def cleanup():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM up_upstream WHERE upstream_id LIKE 'tmp-%'")
    con.execute("DELETE FROM agg_model_group")
    con.execute("DELETE FROM log_usage")
    con.commit()
    print("cleanup ok")


if __name__ == "__main__":
    (cleanup if len(sys.argv) > 1 and sys.argv[1] == "clean" else setup)()

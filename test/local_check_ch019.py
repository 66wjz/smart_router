"""本地 DB 状态检查（CH-019 联调前）"""
import sqlite3

con = sqlite3.connect("smart_router.db")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)
if "log_usage" in tables:
    print("usage rows:", con.execute("SELECT COUNT(*) FROM log_usage").fetchone()[0])
else:
    print("usage rows: NO TABLE YET")
print("api keys:", [(r[0], r[1]) for r in con.execute("SELECT id,name FROM api_api_key LIMIT 5")])
print("upstreams:", [(r[0], r[1]) for r in con.execute("SELECT upstream_id,name FROM up_upstream")])
print("settings:", [(r[0], r[1]) for r in con.execute("SELECT key,value FROM sys_setting")])

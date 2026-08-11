import sqlite3, json
c = sqlite3.connect('smart_router.db')
rows = c.execute("SELECT key, value FROM sys_setting").fetchall()
for k, v in rows:
    print(f"--- {k} ---")
    print(v)

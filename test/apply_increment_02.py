"""执行增量 SQL：02 上游Key池（本地或服务器指定 db）"""
import os
import sqlite3
import sys

SQL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql", "increment", "02_增量_20260809_上游Key池.sql")
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "smart_router.db"


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        with open(SQL_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print(f"[OK] 已执行增量 SQL: {SQL_PATH}")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='up_upstream_key'")]
        print("表存在:", tables)
        rows = conn.execute("SELECT upstream_id, COUNT(*) FROM up_upstream_key GROUP BY upstream_id").fetchall()
        print("各上游 Key 数:", rows)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

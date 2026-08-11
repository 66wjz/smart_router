"""
数据库初始化脚本
执行 sql/01_建表.sql + sql/02_init_data.sql（幂等：先重建表再导入种子数据）
用法：uv run seed.py
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_router.db")
SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")


def drop_all(conn: sqlite3.Connection) -> None:
    """删除所有业务表（幂等重建）"""
    tables = [
        "rule_candidate", "rule_rule", "api_api_key",
        "up_upstream", "pt_pointer", "agg_aggregated_name", "sys_setting",
    ]
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


def run_sql_file(conn: sqlite3.Connection, filename: str) -> None:
    path = os.path.join(SQL_DIR, filename)
    if not os.path.exists(path):
        print(f"[seed] 跳过（文件不存在）: {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    print(f"[seed] 已执行: {filename}")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        print(f"[seed] 初始化数据库: {DB_PATH}")
        drop_all(conn)
        run_sql_file(conn, "01_建表.sql")
        run_sql_file(conn, "02_init_data.sql")
        print("[seed] 初始化完成 ✅")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

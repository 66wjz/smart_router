"""
Repository 基类 - 通用数据库操作
"""

import sqlite3
import threading

from app.core.database import get_conn

_lock = threading.RLock()


class BaseRepository:
    """提供带锁的执行辅助，避免并发写冲突"""

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with _lock:
            conn = get_conn()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with _lock:
            conn = get_conn()
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        with _lock:
            conn = get_conn()
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

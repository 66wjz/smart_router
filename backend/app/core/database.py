"""
数据库连接管理 - SQLite
单进程 uvicorn 部署，全局连接 + 线程锁串行访问。
SQLite 原生支持，无 ORM 依赖。
"""

import os
import sqlite3
import threading

# 数据库文件位于 backend/ 目录下（与 seed.py 保持一致）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "smart_router.db")

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    """获取全局 SQLite 连接（懒加载 + 线程锁）"""
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
        return _conn


def close() -> None:
    """关闭连接（应用退出时调用）"""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None

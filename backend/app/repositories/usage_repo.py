"""
用量统计 Repository - log_usage 表（CH-019）
"""

from app.repositories.base import BaseRepository


class UsageRepository(BaseRepository):
    TABLE = "log_usage"

    def insert_many(self, rows: list[dict]) -> int:
        """批量插入用量记录，返回插入条数"""
        if not rows:
            return 0
        sql = (
            f"INSERT INTO {self.TABLE} "
            f"(ts, api_key_id, api_key_name, upstream_id, upstream_name, model, protocol, stream, "
            f" status, http_status, prompt_tokens, completion_tokens, total_tokens, estimated, "
            f" duration_ms, first_token_ms, error_msg) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = [
            (
                r.get("ts"), r.get("api_key_id"), r.get("api_key_name"),
                r.get("upstream_id"), r.get("upstream_name"), r.get("model"),
                r.get("protocol", "chat"), 1 if r.get("stream") else 0,
                r.get("status", "success"), r.get("http_status", 200),
                r.get("prompt_tokens", 0), r.get("completion_tokens", 0), r.get("total_tokens", 0),
                1 if r.get("estimated") else 0,
                r.get("duration_ms"), r.get("first_token_ms"),
                (r.get("error_msg") or "")[:500],
            )
            for r in rows
        ]
        return self._lock_cursor_batch(sql, params)

    def _lock_cursor_batch(self, sql: str, params: list[tuple]) -> int:
        from app.core.database import get_conn
        from app.repositories.base import _lock
        with _lock:
            conn = get_conn()
            cur = conn.executemany(sql, params)
            conn.commit()
            return cur.rowcount

    def purge_older_than(self, days: int) -> int:
        """删除保留期之前的记录"""
        cutoff = __import__("time").time() - days * 86400
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE ts < ?", (cutoff,))
        return cur.rowcount

    @staticmethod
    def _range_clause(range_name: str) -> tuple[str, tuple]:
        """时间范围 → SQL 条件。today 以本地自然日为界"""
        if range_name == "today":
            return "created_at >= date('now','localtime')", ()
        if range_name == "7d":
            return "ts >= ?", (__import__("time").time() - 7 * 86400,)
        if range_name == "30d":
            return "ts >= ?", (__import__("time").time() - 30 * 86400,)
        return "1=1", ()

    def summary(self, range_name: str = "today") -> dict:
        """全局汇总：总请求/成功/tokens/活跃 Key 数/错误 Top"""
        cond, params = self._range_clause(range_name)
        row = self.query_one(
            f"SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            f"COUNT(DISTINCT CASE WHEN api_key_id IS NOT NULL THEN api_key_id END) AS active_keys "
            f"FROM {self.TABLE} WHERE {cond}",
            params,
        ) or {}
        err_rows = self.query(
            f"SELECT COALESCE(upstream_name, '未知') || '/' || model AS target, COUNT(*) AS cnt "
            f"FROM {self.TABLE} WHERE {cond} AND status != 'success' "
            f"GROUP BY target ORDER BY cnt DESC LIMIT 5",
            params,
        )
        total = row.get("total", 0) or 0
        success = row.get("success_count", 0) or 0
        return {
            "total": total,
            "success_count": success,
            "success_rate": round(success / total, 4) if total else None,
            "total_tokens": row.get("total_tokens", 0) or 0,
            "active_keys": row.get("active_keys", 0) or 0,
            "top_errors": [{"target": r["target"], "count": r["cnt"]} for r in err_rows],
        }

    def by_model(self, range_name: str = "7d") -> list[dict]:
        cond, params = self._range_clause(range_name)
        rows = self.query(
            f"SELECT model, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
            f"COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            f"COALESCE(ROUND(AVG(CASE WHEN status='success' THEN duration_ms END)), 0) AS avg_duration_ms, "
            f"COUNT(DISTINCT upstream_id) AS upstream_count "
            f"FROM {self.TABLE} WHERE {cond} "
            f"GROUP BY model ORDER BY total_tokens DESC LIMIT 200",
            params,
        )
        for r in rows:
            r["error_count"] = (r.get("requests", 0) or 0) - (r.get("success_count", 0) or 0)
        return rows

    def by_key(self, range_name: str = "7d") -> list[dict]:
        cond, params = self._range_clause(range_name)
        rows = self.query(
            f"SELECT api_key_id, api_key_name, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            f"COALESCE(ROUND(AVG(CASE WHEN status='success' THEN duration_ms END)), 0) AS avg_duration_ms "
            f"FROM {self.TABLE} WHERE {cond} AND api_key_id IS NOT NULL "
            f"GROUP BY api_key_id, api_key_name ORDER BY total_tokens DESC LIMIT 200",
            params,
        )
        for r in rows:
            r["error_count"] = r["requests"] - r["success_count"]
        return rows

    def logs(self, range_name: str = "today", page: int = 1, size: int = 50,
             key_id: int | None = None, model: str | None = None, status: str | None = None) -> dict:
        """明细分页查询"""
        cond, params = self._range_clause(range_name)
        where = [cond]
        if key_id is not None:
            where.append("api_key_id = ?")
            params = list(params) + [key_id]
        if model:
            where.append("model = ?")
            params = list(params) + [model]
        if status == "success":
            where.append("status = 'success'")
        elif status == "error":
            where.append("status != 'success'")
        where_sql = " AND ".join(where)
        total = (self.query_one(f"SELECT COUNT(*) AS c FROM {self.TABLE} WHERE {where_sql}", tuple(params)) or {}).get("c", 0)
        rows = self.query(
            f"SELECT * FROM {self.TABLE} WHERE {where_sql} "
            f"ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params) + (size, (max(page, 1) - 1) * size),
        )
        return {"total": total, "page": page, "size": size, "items": rows}

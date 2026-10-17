"""
用量统计 Repository - log_usage 表（CH-019）
"""

from app.repositories.base import BaseRepository


class UsageRepository(BaseRepository):
    TABLE = "log_usage"

    def insert_many(self, rows: list[dict]) -> int:
        """批量插入用量记录，返回插入条数
        CH-021：upstream_model 列可能尚未迁移（旧库），此时退回旧列写法，避免整批丢弃"""
        if not rows:
            return 0
        has_unit_col = self._ensure_unit_column()
        if has_unit_col:
            sql = (
                f"INSERT INTO {self.TABLE} "
                f"(ts, api_key_id, api_key_name, upstream_id, upstream_name, model, upstream_model, "
                f" protocol, stream, status, http_status, prompt_tokens, completion_tokens, total_tokens, "
                f" estimated, duration_ms, first_token_ms, error_msg) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            sql = (
                f"INSERT INTO {self.TABLE} "
                f"(ts, api_key_id, api_key_name, upstream_id, upstream_name, model, protocol, stream, "
                f" status, http_status, prompt_tokens, completion_tokens, total_tokens, estimated, "
                f" duration_ms, first_token_ms, error_msg) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
        params = []
        for r in rows:
            base = (
                r.get("ts"), r.get("api_key_id"), r.get("api_key_name"),
                r.get("upstream_id"), r.get("upstream_name"), r.get("model"),
            )
            if has_unit_col:
                base += (r.get("upstream_model"),)
            base += (
                r.get("protocol", "chat"), 1 if r.get("stream") else 0,
                r.get("status", "success"), r.get("http_status", 200),
                r.get("prompt_tokens", 0), r.get("completion_tokens", 0), r.get("total_tokens", 0),
                1 if r.get("estimated") else 0,
                r.get("duration_ms"), r.get("first_token_ms"),
                (r.get("error_msg") or "")[:500],
            )
            params.append(base)
        return self._lock_cursor_batch(sql, params)

    _unit_col_state: bool | None = None

    def _ensure_unit_column(self) -> bool:
        """检查（并按需创建）upstream_model 列；结果缓存在类上"""
        if UsageRepository._unit_col_state is not None:
            return UsageRepository._unit_col_state
        try:
            cols = self.query(f"PRAGMA table_info({self.TABLE})")
            names = {c.get("name") for c in cols}
            if "upstream_model" not in names:
                self.execute(f"ALTER TABLE {self.TABLE} ADD COLUMN upstream_model TEXT")
                self.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_usage_unit "
                    f"ON {self.TABLE}(upstream_id, upstream_model, ts)"
                )
            UsageRepository._unit_col_state = True
        except Exception:
            UsageRepository._unit_col_state = False
        return bool(UsageRepository._unit_col_state)

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
        """时间范围 → SQL 条件

        CH-022 修复：today 边界必须用请求时间 ts（而非落库时间 created_at）。
        created_at 是批量 flush 写入时间，用它会导致"今日"把历史数据也算进去
        （批量导入/补数据时尤其明显）。
        """
        if range_name == "today":
            from datetime import datetime
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return "ts >= ?", (start.timestamp(),)
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

    def count_in_period(self, start_ts: float, end_ts: float) -> int:
        """指定时间区间内的请求数（CH-022：用于"今日 vs 昨日同期"环比）"""
        row = self.query_one(
            f"SELECT COUNT(*) AS c FROM {self.TABLE} WHERE ts >= ? AND ts < ?",
            (start_ts, end_ts),
        ) or {}
        return row.get("c", 0) or 0

    def daily_trend(self, days: int = 7) -> list[dict]:
        """按本地自然日聚合最近 N 天（含今天），无数据的日期补 0（CH-022 仪表盘趋势图）"""
        from datetime import datetime, timedelta

        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
        rows = self.query(
            f"SELECT date(ts, 'unixepoch', 'localtime') AS d, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens "
            f"FROM {self.TABLE} WHERE ts >= ? "
            f"GROUP BY d ORDER BY d",
            (start.timestamp(),),
        )
        by_day = {r["d"]: r for r in rows}
        result = []
        for i in range(days):
            day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            r = by_day.get(day) or {}
            result.append({
                "date": day[5:],
                "requests": r.get("requests", 0) or 0,
                "success_count": r.get("success_count", 0) or 0,
                "total_tokens": r.get("total_tokens", 0) or 0,
            })
        return result

    def by_upstream(self, range_name: str = "7d") -> list[dict]:
        """按上游源聚合（CH-022 仪表盘贡献占比）"""
        cond, params = self._range_clause(range_name)
        rows = self.query(
            f"SELECT upstream_id, upstream_name, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens "
            f"FROM {self.TABLE} WHERE {cond} AND upstream_id IS NOT NULL "
            f"GROUP BY upstream_id, upstream_name ORDER BY total_tokens DESC LIMIT 50",
            params,
        )
        total_tokens = sum((r.get("total_tokens") or 0) for r in rows)
        for r in rows:
            r["error_count"] = (r.get("requests") or 0) - (r.get("success_count") or 0)
            r["share"] = round((r.get("total_tokens") or 0) / total_tokens, 4) if total_tokens else 0
        return rows

    def by_request_model(self, range_name: str = "7d") -> list[dict]:
        """按客户端请求的模型名聚合（CH-022 仪表盘聚合组概览）"""
        cond, params = self._range_clause(range_name)
        rows = self.query(
            f"SELECT model, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens "
            f"FROM {self.TABLE} WHERE {cond} AND model IS NOT NULL "
            f"GROUP BY model",
            params,
        )
        return [
            {
                "model": r["model"],
                "requests": r.get("requests", 0) or 0,
                "success_count": r.get("success_count", 0) or 0,
                "total_tokens": r.get("total_tokens", 0) or 0,
            }
            for r in rows
        ]

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

    def by_unit(self, range_name: str = "7d") -> list[dict]:
        """按「上游源 × 上游真实模型名」聚合（CH-021 号池消耗核算）

        老数据（CH-021 之前）没有 upstream_model，用 '（历史）' 归并，避免丢量。
        """
        cond, params = self._range_clause(range_name)
        if not self._ensure_unit_column():
            return []
        rows = self.query(
            f"SELECT upstream_id, upstream_name, "
            f"COALESCE(NULLIF(upstream_model, ''), model) AS upstream_model, "
            f"COUNT(*) AS requests, "
            f"SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count, "
            f"COUNT(DISTINCT model) AS request_models, "
            f"COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
            f"COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
            f"COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            f"COALESCE(ROUND(AVG(CASE WHEN status='success' THEN duration_ms END)), 0) AS avg_duration_ms, "
            f"MAX(ts) AS last_ts "
            f"FROM {self.TABLE} WHERE {cond} AND upstream_id IS NOT NULL "
            f"GROUP BY upstream_id, upstream_name, upstream_model "
            f"ORDER BY total_tokens DESC LIMIT 500",
            params,
        )
        for r in rows:
            r["error_count"] = (r.get("requests", 0) or 0) - (r.get("success_count", 0) or 0)
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

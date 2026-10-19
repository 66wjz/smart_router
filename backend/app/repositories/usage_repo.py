"""
用量统计 Repository - log_usage 表（CH-019）
"""

from app.repositories.base import BaseRepository


class UsageRepository(BaseRepository):
    TABLE = "log_usage"
    DETAIL_TABLE = "log_usage_detail"

    def insert_many(self, rows: list[dict]) -> int:
        """批量插入用量记录，返回插入条数

        CH-021：upstream_model 列可能尚未迁移（旧库），此时退回旧列写法，避免整批丢弃
        CH-038：新增 cache_read_tokens / cache_write_tokens / attempt_count 三列；
                请求详情写入 log_usage_detail（与主表同一事务，靠 lastrowid 关联）
        """
        if not rows:
            return 0
        cols = self._columns()
        extra_cols = [c for c in ("upstream_model", "cache_read_tokens",
                                  "cache_write_tokens", "attempt_count") if c in cols]
        names = (
            ["ts", "api_key_id", "api_key_name", "upstream_id", "upstream_name", "model"]
            + extra_cols
            + ["protocol", "stream", "status", "http_status", "prompt_tokens",
               "completion_tokens", "total_tokens", "estimated", "duration_ms",
               "first_token_ms", "error_msg"]
        )
        sql = (
            f"INSERT INTO {self.TABLE} ({', '.join(names)}) "
            f"VALUES ({', '.join('?' * len(names))})"
        )
        has_detail = self.DETAIL_TABLE in self._tables()

        from app.core.database import get_conn
        from app.repositories.base import _lock

        inserted = 0
        with _lock:
            conn = get_conn()
            for r in rows:
                params = [
                    r.get("ts"), r.get("api_key_id"), r.get("api_key_name"),
                    r.get("upstream_id"), r.get("upstream_name"), r.get("model"),
                ]
                for c in extra_cols:
                    if c == "upstream_model":
                        params.append(r.get("upstream_model"))
                    else:
                        params.append(int(r.get(c) or 0))
                params += [
                    r.get("protocol", "chat"), 1 if r.get("stream") else 0,
                    r.get("status", "success"), r.get("http_status", 200),
                    r.get("prompt_tokens", 0), r.get("completion_tokens", 0),
                    r.get("total_tokens", 0), 1 if r.get("estimated") else 0,
                    r.get("duration_ms"), r.get("first_token_ms"),
                    (r.get("error_msg") or "")[:500],
                ]
                cur = conn.execute(sql, tuple(params))
                inserted += 1
                detail = r.get("detail")
                if detail and has_detail:
                    self._insert_detail(conn, cur.lastrowid, detail)
            conn.commit()
        return inserted

    @staticmethod
    def _insert_detail(conn, log_id: int, detail: dict) -> None:
        """写详情行（与主表同事务，失败不影响主表已插入的行）"""
        try:
            conn.execute(
                "INSERT OR REPLACE INTO log_usage_detail "
                "(log_id, request_headers, request_body, forward_body, response_body, attempts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    log_id,
                    detail.get("request_headers"),
                    detail.get("request_body"),
                    detail.get("forward_body"),
                    detail.get("response_body"),
                    detail.get("attempts"),
                ),
            )
        except Exception:
            pass

    _cols_state: dict = {}

    def _columns(self) -> set[str]:
        """主表列名（带缓存，避免每条批量插入都 PRAGMA）"""
        key = f"{self.TABLE}:{id(self)}"
        cached = UsageRepository._cols_state.get(key)
        if cached is not None:
            return cached
        try:
            names = {c.get("name") for c in self.query(f"PRAGMA table_info({self.TABLE})")}
        except Exception:
            names = set()
        UsageRepository._cols_state[key] = names
        return names

    _tables_state: set | None = None

    def _tables(self) -> set[str]:
        if UsageRepository._tables_state is not None:
            return UsageRepository._tables_state
        try:
            rows = self.query("SELECT name FROM sqlite_master WHERE type='table'")
            UsageRepository._tables_state = {r["name"] for r in rows}
        except Exception:
            UsageRepository._tables_state = set()
        return UsageRepository._tables_state

    def _ensure_unit_column(self) -> bool:
        """幂等补齐 log_usage 的增量列（CH-021 upstream_model + CH-038 三列）

        老库缺列时运行期补上，避免整批写入失败；补齐后清空列缓存。
        """
        wanted = {
            "upstream_model": "TEXT",
            "cache_read_tokens": "INTEGER DEFAULT 0",
            "cache_write_tokens": "INTEGER DEFAULT 0",
            "attempt_count": "INTEGER DEFAULT 1",
        }
        try:
            names = {c.get("name") for c in self.query(f"PRAGMA table_info({self.TABLE})")}
            changed = False
            for col, ddl in wanted.items():
                if col not in names:
                    self.execute(f"ALTER TABLE {self.TABLE} ADD COLUMN {col} {ddl}")
                    changed = True
            if "upstream_model" not in names:
                self.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_usage_unit "
                    f"ON {self.TABLE}(upstream_id, upstream_model, ts)"
                )
            if changed:
                UsageRepository._cols_state.clear()
            return "upstream_model" in names or changed
        except Exception:
            return False

    def _lock_cursor_batch(self, sql: str, params: list[tuple]) -> int:
        from app.core.database import get_conn
        from app.repositories.base import _lock
        with _lock:
            conn = get_conn()
            cur = conn.executemany(sql, params)
            conn.commit()
            return cur.rowcount

    def purge_older_than(self, days: int) -> int:
        """删除保留期之前的记录（主表 + 详情表同步，CH-038）

        先删详情再删主表：当前虽无外键，但保持顺序可让「详情行数 ≤ 主表行数」
        始终成立，避免中途失败留下孤儿详情。
        """
        cutoff = __import__("time").time() - days * 86400
        detail_deleted = 0
        if self.DETAIL_TABLE in self._tables():
            from app.core.database import get_conn
            from app.repositories.base import _lock
            with _lock:
                conn = get_conn()
                cur = conn.execute(
                    f"DELETE FROM {self.DETAIL_TABLE} WHERE log_id IN "
                    f"(SELECT id FROM {self.TABLE} WHERE ts < ?)",
                    (cutoff,),
                )
                detail_deleted = cur.rowcount or 0
                conn.commit()
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE ts < ?", (cutoff,))
        if detail_deleted:
            import logging
            logging.getLogger("router").info(
                f"[usage] 清理过期记录 主表 {cur.rowcount or 0} 条 / 详情 {detail_deleted} 条"
            )
        return cur.rowcount

    def get_detail(self, log_id: int) -> dict | None:
        """读取单条请求详情（CH-038）；主表无此行返回 None"""
        row = self.query_one(f"SELECT * FROM {self.TABLE} WHERE id = ?", (log_id,))
        if not row:
            return None
        detail = None
        if self.DETAIL_TABLE in self._tables():
            detail = self.query_one(
                f"SELECT * FROM {self.DETAIL_TABLE} WHERE log_id = ?", (log_id,)
            )
        return {"summary": row, "detail": detail}

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

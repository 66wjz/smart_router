"""
聚合探测配置 Repository - agg_probe_config 表（CH-021）

一行 = 一个聚合组的探测策略。与 agg_model_group 解耦：
自动发现的聚合组也能单独配置探测，且不会因此变成"已手动配置"。

字段留空（NULL）表示跟随全局 sys_setting.latency_probe。
"""

import json

from app.repositories.base import BaseRepository


class ProbeConfigRepository(BaseRepository):
    TABLE = "agg_probe_config"

    @staticmethod
    def _parse_schedule(raw) -> dict:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def list_all(self) -> dict[str, dict]:
        """{聚合名: {enabled, interval_seconds, slow_threshold_seconds, sort_mode, schedule}}"""
        try:
            rows = self.query(
                f"SELECT model, enabled, interval_seconds, slow_threshold_seconds, sort_mode, schedule "
                f"FROM {self.TABLE} ORDER BY model"
            )
        except Exception:
            return {}
        result = {}
        for r in rows:
            result[r["model"]] = {
                "enabled": bool(r.get("enabled", 0)),
                "interval_seconds": r.get("interval_seconds"),
                "slow_threshold_seconds": r.get("slow_threshold_seconds"),
                "sort_mode": r.get("sort_mode") or "stable",
                "schedule": self._parse_schedule(r.get("schedule")),
            }
        return result

    def upsert(self, model: str, data: dict) -> None:
        self.execute(
            f"INSERT INTO {self.TABLE} "
            f"(model, enabled, interval_seconds, slow_threshold_seconds, sort_mode, schedule) "
            f"VALUES (?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT(model) DO UPDATE SET "
            f"enabled = excluded.enabled, interval_seconds = excluded.interval_seconds, "
            f"slow_threshold_seconds = excluded.slow_threshold_seconds, "
            f"sort_mode = excluded.sort_mode, schedule = excluded.schedule, "
            f"updated_at = CURRENT_TIMESTAMP",
            (
                model,
                1 if data.get("enabled") else 0,
                data.get("interval_seconds"),
                data.get("slow_threshold_seconds"),
                data.get("sort_mode") or "stable",
                json.dumps(self._parse_schedule(data.get("schedule")), ensure_ascii=False),
            ),
        )

    def delete(self, model: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE model = ?", (model,))
        return cur.rowcount > 0

"""
探测模板 Repository - agg_probe_template 表（CH-023）

模板定义一套探测节奏，多个聚合可引用同一模板；模板值优先于聚合自配字段。
"""

import json

from app.repositories.base import BaseRepository


class ProbeTemplateRepository(BaseRepository):
    TABLE = "agg_probe_template"

    @staticmethod
    def _parse_schedule(raw) -> dict:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def list_all(self) -> list[dict]:
        """模板列表（按 id 升序）；表不存在时返回空"""
        try:
            rows = self.query(
                f"SELECT id, name, interval_seconds, slow_threshold_seconds, sort_mode, "
                f"schedule, remark FROM {self.TABLE} ORDER BY id"
            )
        except Exception:
            return []
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "interval_seconds": r.get("interval_seconds"),
                "slow_threshold_seconds": r.get("slow_threshold_seconds"),
                "sort_mode": r.get("sort_mode") or "stable",
                "schedule": self._parse_schedule(r.get("schedule")),
                "remark": r.get("remark") or "",
            }
            for r in rows
        ]

    def get(self, template_id: int) -> dict | None:
        for t in self.list_all():
            if t["id"] == template_id:
                return t
        return None

    def create(self, data: dict) -> int:
        cur = self.execute(
            f"INSERT INTO {self.TABLE} "
            f"(name, interval_seconds, slow_threshold_seconds, sort_mode, schedule, remark) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (
                data["name"],
                data.get("interval_seconds"),
                data.get("slow_threshold_seconds"),
                data.get("sort_mode") or "stable",
                json.dumps(self._parse_schedule(data.get("schedule")), ensure_ascii=False),
                data.get("remark") or "",
            ),
        )
        return cur.lastrowid

    def update(self, template_id: int, data: dict) -> bool:
        cur = self.execute(
            f"UPDATE {self.TABLE} SET name = ?, interval_seconds = ?, slow_threshold_seconds = ?, "
            f"sort_mode = ?, schedule = ?, remark = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?",
            (
                data["name"],
                data.get("interval_seconds"),
                data.get("slow_threshold_seconds"),
                data.get("sort_mode") or "stable",
                json.dumps(self._parse_schedule(data.get("schedule")), ensure_ascii=False),
                data.get("remark") or "",
                template_id,
            ),
        )
        return cur.rowcount > 0

    def delete(self, template_id: int) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (template_id,))
        return cur.rowcount > 0

"""
统一聚合实体 Repository - agg_unified 表（CH-023）

一行 = 一个聚合名，用 kind 区分两类语义：
  static：固定成员列表（原 agg_model_group），支持异名成员
  rule  ：手写聚合名（原 agg_aggregated_name），成员由路由规则在运行时匹配

探测字段（probe_enabled / template_id / interval_seconds / slow_threshold_seconds /
sort_mode / schedule）统一存在本表；template_id 非空时模板值优先。
"""

import json

from app.repositories.base import BaseRepository


class AggregationRepository(BaseRepository):
    TABLE = "agg_unified"

    @staticmethod
    def _parse_members(raw) -> list[dict]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else []
            except Exception:
                raw = []
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            if isinstance(item, str) and item:
                result.append({"upstream": item, "model": None, "weight": 1})
            elif isinstance(item, dict) and item.get("upstream"):
                result.append({
                    "upstream": str(item["upstream"]),
                    "model": str(item["model"]) if item.get("model") else None,
                    "weight": int(item.get("weight", 1) or 1),
                })
        return result

    @staticmethod
    def _parse_schedule(raw) -> dict:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def list_all(self) -> dict[str, dict]:
        """{聚合名: {kind, members, enabled, probe_enabled, template_id, ...}}；表不存在时返回空"""
        try:
            rows = self.query(
                f"SELECT name, kind, members, enabled, probe_enabled, template_id, sort_mode, "
                f"interval_seconds, slow_threshold_seconds, schedule, remark "
                f"FROM {self.TABLE} ORDER BY kind, name"
            )
        except Exception:
            return {}
        result = {}
        for r in rows:
            result[r["name"]] = {
                "name": r["name"],
                "kind": r.get("kind") or "static",
                "members": self._parse_members(r.get("members")),
                "enabled": bool(r.get("enabled", 1)),
                "probe_enabled": bool(r.get("probe_enabled", 0)),
                "template_id": r.get("template_id"),
                "sort_mode": r.get("sort_mode") or "stable",
                "interval_seconds": r.get("interval_seconds"),
                "slow_threshold_seconds": r.get("slow_threshold_seconds"),
                "schedule": self._parse_schedule(r.get("schedule")),
                "remark": r.get("remark") or "",
            }
        return result

    def upsert(self, name: str, data: dict) -> None:
        """新建或更新一个聚合（未提供的字段保持原值，用 COALESCE 实现部分更新语义）"""
        kind = data.get("kind") or "static"
        members = self._parse_members(data.get("members"))
        schedule = json.dumps(self._parse_schedule(data.get("schedule")), ensure_ascii=False)
        self.execute(
            f"INSERT INTO {self.TABLE} "
            f"(name, kind, members, enabled, probe_enabled, template_id, sort_mode, "
            f" interval_seconds, slow_threshold_seconds, schedule, remark) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT(name) DO UPDATE SET "
            f"kind = excluded.kind, members = excluded.members, enabled = excluded.enabled, "
            f"probe_enabled = excluded.probe_enabled, template_id = excluded.template_id, "
            f"sort_mode = excluded.sort_mode, interval_seconds = excluded.interval_seconds, "
            f"slow_threshold_seconds = excluded.slow_threshold_seconds, "
            f"schedule = excluded.schedule, remark = excluded.remark, "
            f"updated_at = CURRENT_TIMESTAMP",
            (
                name,
                kind,
                json.dumps(members, ensure_ascii=False),
                1 if data.get("enabled", True) else 0,
                1 if data.get("probe_enabled") else 0,
                data.get("template_id"),
                data.get("sort_mode") or "stable",
                data.get("interval_seconds"),
                data.get("slow_threshold_seconds"),
                schedule,
                data.get("remark") or "",
            ),
        )

    def delete(self, name: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE name = ?", (name,))
        return cur.rowcount > 0

    def clear_template_refs(self, template_id: int) -> list[str]:
        """模板被删除时：把引用它的聚合 template_id 置空，返回受影响的聚合名"""
        rows = self.query(
            f"SELECT name FROM {self.TABLE} WHERE template_id = ? ORDER BY name", (template_id,)
        )
        names = [r["name"] for r in rows]
        if names:
            self.execute(
                f"UPDATE {self.TABLE} SET template_id = NULL, updated_at = CURRENT_TIMESTAMP "
                f"WHERE template_id = ?",
                (template_id,),
            )
        return names

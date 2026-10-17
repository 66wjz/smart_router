"""
上游源 Repository - up_upstream 表
"""

import json

from app.repositories.base import BaseRepository


class UpstreamRepository(BaseRepository):
    TABLE = "up_upstream"

    @staticmethod
    def _parse_models(raw) -> list[dict]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else []
            except Exception:
                raw = []
        if not isinstance(raw, list):
            return []
        result = []
        for idx, item in enumerate(raw):
            if isinstance(item, str) and item:
                result.append({"name": item, "enabled": 1, "order": idx})
            elif isinstance(item, dict) and item.get("name"):
                entry = {"name": str(item["name"])}
                protocol = item.get("protocol")
                if protocol:
                    entry["protocol"] = str(protocol)
                entry["enabled"] = 1 if item.get("enabled", True) else 0
                entry["order"] = item.get("order", idx)
                result.append(entry)
        return result

    @staticmethod
    def _dump_models(models) -> str:
        normalized = UpstreamRepository._parse_models(models)
        return json.dumps(normalized, ensure_ascii=False)

    @staticmethod
    def _parse_groups(raw, legacy_group: str = "free") -> list[str]:
        """groups JSON 数组解析；为空时回退 [group_name]（CH-016 兼容存量）"""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else []
            except Exception:
                raw = []
        if isinstance(raw, list) and raw:
            return [str(g) for g in raw if g]
        return [legacy_group or "free"]

    def _fill(self, row: dict) -> dict:
        row["models"] = self._parse_models(row.get("models"))
        row["groups"] = self._parse_groups(row.get("groups"), row.get("group_name", "free"))
        return row

    def list_all(self) -> list[dict]:
        rows = self.query(f"SELECT * FROM {self.TABLE} ORDER BY id")
        for r in rows:
            self._fill(r)
        return rows

    def get_by_id(self, upstream_id: str) -> dict | None:
        row = self.query_one(f"SELECT * FROM {self.TABLE} WHERE upstream_id = ?", (upstream_id,))
        if row:
            self._fill(row)
        return row

    def create(self, data: dict) -> bool:
        if self.get_by_id(data["id"]):
            return False
        groups = data.get("groups") or [data.get("group", "free")]
        self.execute(
            f"INSERT INTO {self.TABLE} (upstream_id, name, base_url, api_key, format, group_name, groups, probe_enabled, models, smart_retry) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["id"], data.get("name", ""), data.get("base_url", ""),
             data.get("api_key") or "", data.get("format", "openai"),
             groups[0], json.dumps(groups, ensure_ascii=False),
             1 if data.get("probe_enabled", True) else 0,
             self._dump_models(data.get("models")),
             1 if data.get("smart_retry") else 0),
        )
        return True

    def update(self, upstream_id: str, data: dict) -> bool:
        if not self.get_by_id(upstream_id):
            return False
        allowed = {"name", "base_url", "api_key", "format", "group", "groups", "probe_enabled", "enabled", "models", "smart_retry"}
        sets, params = [], []
        field_map = {"group": "group_name"}
        for k in allowed:
            if k in data:
                col = field_map.get(k, k)
                val = data[k]
                if k in ("probe_enabled", "enabled", "smart_retry"):
                    val = 1 if val else 0
                elif k == "models":
                    val = self._dump_models(val)
                elif k == "groups":
                    groups = [str(g) for g in (val or []) if g] or ["free"]
                    val = json.dumps(groups, ensure_ascii=False)
                    sets.append("group_name = ?")
                    params.append(groups[0])
                sets.append(f"{col} = ?")
                params.append(val)
        if not sets:
            return True
        params.append(upstream_id)
        self.execute(f"UPDATE {self.TABLE} SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE upstream_id = ?", tuple(params))
        return True

    def delete(self, upstream_id: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE upstream_id = ?", (upstream_id,))
        return cur.rowcount > 0

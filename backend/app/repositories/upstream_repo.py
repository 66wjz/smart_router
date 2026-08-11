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
        for item in raw:
            if isinstance(item, str) and item:
                result.append({"name": item})
            elif isinstance(item, dict) and item.get("name"):
                entry = {"name": str(item["name"])}
                protocol = item.get("protocol")
                if protocol:
                    entry["protocol"] = str(protocol)
                result.append(entry)
        return result

    @staticmethod
    def _dump_models(models) -> str:
        normalized = UpstreamRepository._parse_models(models)
        return json.dumps(normalized, ensure_ascii=False)

    def list_all(self) -> list[dict]:
        rows = self.query(f"SELECT * FROM {self.TABLE} ORDER BY id")
        for r in rows:
            r["models"] = self._parse_models(r.get("models"))
        return rows

    def get_by_id(self, upstream_id: str) -> dict | None:
        row = self.query_one(f"SELECT * FROM {self.TABLE} WHERE upstream_id = ?", (upstream_id,))
        if row:
            row["models"] = self._parse_models(row.get("models"))
        return row

    def create(self, data: dict) -> bool:
        if self.get_by_id(data["id"]):
            return False
        self.execute(
            f"INSERT INTO {self.TABLE} (upstream_id, name, base_url, api_key, format, group_name, probe_enabled, models, smart_retry) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["id"], data.get("name", ""), data.get("base_url", ""),
             data.get("api_key") or "", data.get("format", "openai"),
             data.get("group", "free"), 1 if data.get("probe_enabled", True) else 0,
             self._dump_models(data.get("models")),
             1 if data.get("smart_retry") else 0),
        )
        return True

    def update(self, upstream_id: str, data: dict) -> bool:
        if not self.get_by_id(upstream_id):
            return False
        allowed = {"name", "base_url", "api_key", "format", "group", "probe_enabled", "enabled", "models", "smart_retry"}
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

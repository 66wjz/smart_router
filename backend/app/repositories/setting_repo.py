"""
系统参数 Repository - sys_setting 表
key-value 结构，value 存 JSON 字符串
"""

import json

from app.repositories.base import BaseRepository


class SettingRepository(BaseRepository):
    TABLE = "sys_setting"

    def get(self, key: str, default=None):
        row = self.query_one(f"SELECT value FROM {self.TABLE} WHERE key = ?", (key,))
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set(self, key: str, value) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        self.execute(
            f"INSERT INTO {self.TABLE} (key, value) VALUES (?, ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (key, raw),
        )

    def get_all(self) -> dict:
        rows = self.query(f"SELECT key, value FROM {self.TABLE}")
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result

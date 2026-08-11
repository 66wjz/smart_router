"""
API Key Repository - api_api_key 表
"""

from app.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository):
    TABLE = "api_api_key"

    def list_all(self) -> list[dict]:
        return self.query(f"SELECT * FROM {self.TABLE} ORDER BY id")

    def get_by_key(self, key_value: str) -> dict | None:
        return self.query_one(f"SELECT * FROM {self.TABLE} WHERE key_value = ?", (key_value,))

    def create(self, name: str, key_value: str, groups: str, enabled: bool) -> bool:
        """创建，key 重复返回 False"""
        if self.get_by_key(key_value):
            return False
        self.execute(
            f"INSERT INTO {self.TABLE} (name, key_value, groups, enabled) VALUES (?, ?, ?, ?)",
            (name, key_value, groups, 1 if enabled else 0),
        )
        return True

    def update(self, key_value: str, name: str | None = None, groups: str | None = None,
               enabled: bool | None = None) -> bool:
        """更新（key 字段不可改），不存在返回 False"""
        if not self.get_by_key(key_value):
            return False
        sets, params = [], []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if groups is not None:
            sets.append("groups = ?")
            params.append(groups)
        if enabled is not None:
            sets.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not sets:
            return True
        params.append(key_value)
        self.execute(f"UPDATE {self.TABLE} SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE key_value = ?", tuple(params))
        return True

    def delete(self, key_value: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE key_value = ?", (key_value,))
        return cur.rowcount > 0

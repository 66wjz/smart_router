"""
上游源 Key 池 Repository - up_upstream_key 表
一个上游源对应多个 API Key
"""

from app.repositories.base import BaseRepository


class UpstreamKeyRepository(BaseRepository):
    TABLE = "up_upstream_key"

    def list_by_upstream(self, upstream_id: str) -> list[dict]:
        return self.query(
            f"SELECT id, api_key, enabled FROM {self.TABLE} WHERE upstream_id = ? ORDER BY id",
            (upstream_id,),
        )

    def replace(self, upstream_id: str, keys: list[str]) -> None:
        """整体替换 Key 池（删旧插新）"""
        self.execute(f"DELETE FROM {self.TABLE} WHERE upstream_id = ?", (upstream_id,))
        for k in keys:
            k = k.strip()
            if k:
                self.execute(
                    f"INSERT INTO {self.TABLE} (upstream_id, api_key) VALUES (?, ?)",
                    (upstream_id, k),
                )

    def delete_by_upstream(self, upstream_id: str) -> None:
        self.execute(f"DELETE FROM {self.TABLE} WHERE upstream_id = ?", (upstream_id,))

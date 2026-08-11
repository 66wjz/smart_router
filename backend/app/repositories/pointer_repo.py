"""
模型别名 Repository - pt_pointer 表
"""

from app.repositories.base import BaseRepository


class PointerRepository(BaseRepository):
    TABLE = "pt_pointer"

    def list_all(self) -> list[dict]:
        rows = self.query(f"SELECT * FROM {self.TABLE} ORDER BY id")
        return [{
            "name": r["name"],
            "target_model": r["target_model"],
            "upstream": r["upstream_id"],
        } for r in rows]

    def get_by_name(self, name: str) -> dict | None:
        return self.query_one(f"SELECT * FROM {self.TABLE} WHERE name = ?", (name,))

    def create(self, name: str, target_model: str, upstream_id: str) -> bool:
        if self.get_by_name(name):
            return False
        self.execute(
            f"INSERT INTO {self.TABLE} (name, target_model, upstream_id) VALUES (?, ?, ?)",
            (name, target_model, upstream_id),
        )
        return True

    def update(self, name: str, target_model: str | None = None, upstream_id: str | None = None) -> bool:
        if not self.get_by_name(name):
            return False
        sets, params = [], []
        if target_model is not None:
            sets.append("target_model = ?")
            params.append(target_model)
        if upstream_id is not None:
            sets.append("upstream_id = ?")
            params.append(upstream_id)
        if not sets:
            return True
        params.append(name)
        self.execute(f"UPDATE {self.TABLE} SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE name = ?", tuple(params))
        return True

    def delete(self, name: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE name = ?", (name,))
        return cur.rowcount > 0

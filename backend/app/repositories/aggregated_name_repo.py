"""
聚合模型名 Repository - agg_aggregated_name 表
"""

from app.repositories.base import BaseRepository


class AggregatedNameRepository(BaseRepository):
    TABLE = "agg_aggregated_name"

    def list_names(self) -> list[str]:
        rows = self.query(f"SELECT name FROM {self.TABLE} ORDER BY id")
        return [r["name"] for r in rows]

    def replace_all(self, names: list[str]) -> None:
        conn = None
        try:
            from app.core.database import get_conn
            conn = get_conn()
            with conn:
                conn.execute(f"DELETE FROM {self.TABLE}")
                for n in names:
                    conn.execute(f"INSERT INTO {self.TABLE} (name) VALUES (?)", (n,))
        finally:
            if conn:
                conn.commit()

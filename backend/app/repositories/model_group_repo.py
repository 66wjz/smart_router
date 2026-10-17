"""
同名模型聚合组 Repository - agg_model_group 表（CH-019 二期）

用途：让"同名模型自动聚合"可查看、可编辑、可控。
- 未配置任何行的模型 → 自动聚合（沿用 collect_model_upstreams 的自动发现）
- 存在行的模型 → 以配置为准（勾选哪些源、顺序如何、是否启用）

表结构：一行 = 一个模型名的聚合配置
  model     模型名（唯一）
  upstreams JSON 数组，顺序即候选优先级 [{upstream_id, weight?}]
  enabled   1/0 该同名聚合是否启用（0 时退化为单源直连）
"""

import json

from app.repositories.base import BaseRepository


class ModelGroupRepository(BaseRepository):
    TABLE = "agg_model_group"

    @staticmethod
    def _parse_upstreams(raw) -> list[dict]:
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
                result.append({"upstream": item, "weight": 1})
            elif isinstance(item, dict) and item.get("upstream"):
                result.append({
                    "upstream": str(item["upstream"]),
                    "weight": int(item.get("weight", 1) or 1),
                })
        return result

    def list_all(self) -> dict[str, dict]:
        """返回 {model: {upstreams: [...], enabled: bool}}；表不存在时返回空"""
        try:
            rows = self.query(f"SELECT model, upstreams, enabled FROM {self.TABLE} ORDER BY model")
        except Exception:
            return {}
        return {
            r["model"]: {
                "upstreams": self._parse_upstreams(r["upstreams"]),
                "enabled": bool(r.get("enabled", 1)),
            }
            for r in rows
        }

    def upsert(self, model: str, upstreams: list[dict], enabled: bool = True) -> None:
        self.execute(
            f"INSERT INTO {self.TABLE} (model, upstreams, enabled) VALUES (?, ?, ?) "
            f"ON CONFLICT(model) DO UPDATE SET upstreams = excluded.upstreams, enabled = excluded.enabled, "
            f"updated_at = CURRENT_TIMESTAMP",
            (model, json.dumps(self._parse_upstreams(upstreams), ensure_ascii=False), 1 if enabled else 0),
        )

    def delete(self, model: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE model = ?", (model,))
        return cur.rowcount > 0

    def delete_many(self, models: list[str]) -> None:
        for m in models:
            self.delete(m)

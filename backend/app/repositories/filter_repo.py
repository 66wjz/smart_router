"""
请求过滤规则 Repository - filter_rule 表（CH-041）

规则用于「转发前过滤」：命中规则的请求不会发到对应上游源，
避免触发上游黑名单（如 WorkBuddy 的非官方 agent 客户端拦截）。
"""

import json

from app.repositories.base import BaseRepository


class FilterRuleRepository(BaseRepository):
    TABLE = "filter_rule"

    @staticmethod
    def _parse_upstream_ids(raw) -> list[str]:
        """upstream_ids 存 JSON 数组；空/null 表示「作用于全部上游源」"""
        if raw is None or raw == "":
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return []
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw if x]

    def list_all(self) -> list[dict]:
        """全部规则（按 id 升序）；表不存在时返回空列表（容忍未迁移的库）"""
        try:
            rows = self.query(
                f"SELECT id, name, enabled, target, pattern, upstream_ids, action, remark "
                f"FROM {self.TABLE} ORDER BY id"
            )
        except Exception:
            return []
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "enabled": bool(r.get("enabled")),
                "target": r.get("target") or "system_first_line",
                "pattern": r.get("pattern") or "",
                "upstream_ids": self._parse_upstream_ids(r.get("upstream_ids")),
                "action": r.get("action") or "skip",
                "remark": r.get("remark") or "",
            }
            for r in rows
        ]

    def create(self, data: dict) -> int:
        ids = self._parse_upstream_ids(data.get("upstream_ids"))
        cur = self.execute(
            f"INSERT INTO {self.TABLE} "
            f"(name, enabled, target, pattern, upstream_ids, action, remark) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data["name"],
                1 if data.get("enabled") else 0,
                data.get("target") or "system_first_line",
                data["pattern"],
                json.dumps(ids, ensure_ascii=False) if ids else None,
                data.get("action") or "skip",
                data.get("remark") or "",
            ),
        )
        return cur.lastrowid

    def update(self, rule_id: int, data: dict) -> bool:
        ids = self._parse_upstream_ids(data.get("upstream_ids"))
        cur = self.execute(
            f"UPDATE {self.TABLE} SET name = ?, enabled = ?, target = ?, pattern = ?, "
            f"upstream_ids = ?, action = ?, remark = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?",
            (
                data["name"],
                1 if data.get("enabled") else 0,
                data.get("target") or "system_first_line",
                data["pattern"],
                json.dumps(ids, ensure_ascii=False) if ids else None,
                data.get("action") or "skip",
                data.get("remark") or "",
                rule_id,
            ),
        )
        return cur.rowcount > 0

    def delete(self, rule_id: int) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (rule_id,))
        return cur.rowcount > 0

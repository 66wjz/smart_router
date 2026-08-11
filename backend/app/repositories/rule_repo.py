"""
路由规则 Repository - rule_rule + rule_candidate 表
规则与候选模型为父子结构，事务内一起读写。
"""

import json

from app.repositories.base import BaseRepository


class RuleRepository(BaseRepository):
    TABLE = "rule_rule"
    CAND_TABLE = "rule_candidate"

    # ---------- 查询 ----------

    def list_all(self) -> list[dict]:
        """返回完整规则结构（含候选模型）"""
        rules = self.query(f"SELECT * FROM {self.TABLE} ORDER BY sort_order, id")
        cands = self.query(f"SELECT * FROM {self.CAND_TABLE} ORDER BY id")
        cands_by_rule: dict[int, list] = {}
        for c in cands:
            cands_by_rule.setdefault(c["rule_id"], []).append({
                "model": c["model"],
                "upstream": c["upstream_id"],
                "weight": c["weight"],
                "priority": c["priority"],
                "max_context": c["max_context"],
                "max_output": c["max_output"],
            })
        result = []
        for r in rules:
            try:
                match = json.loads(r["match_json"]) if r["match_json"] else {}
            except json.JSONDecodeError:
                match = {}
            result.append({
                "name": r["name"],
                "match": match,
                "candidates": cands_by_rule.get(r["id"], []),
            })
        return result

    # ---------- 写入（整体替换） ----------

    def replace_all(self, rules: list[dict]) -> None:
        """事务内删除旧规则 + 插入新规则，保证原子性"""
        conn = None
        try:
            from app.core.database import get_conn
            conn = get_conn()
            with conn:  # 事务上下文
                conn.execute(f"DELETE FROM {self.CAND_TABLE}")
                conn.execute(f"DELETE FROM {self.TABLE}")
                for i, rule in enumerate(rules):
                    match = json.dumps(rule.get("match", {}), ensure_ascii=False)
                    cur = conn.execute(
                        f"INSERT INTO {self.TABLE} (name, match_json, sort_order) VALUES (?, ?, ?)",
                        (rule.get("name", ""), match, i),
                    )
                    rule_id = cur.lastrowid
                    for c in rule.get("candidates", []):
                        conn.execute(
                            f"INSERT INTO {self.CAND_TABLE} (rule_id, model, upstream_id, weight, priority, max_context, max_output) "
                            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (rule_id, c.get("model", ""), c.get("upstream", ""),
                             c.get("weight", 1), c.get("priority", 1),
                             c.get("max_context"), c.get("max_output")),
                        )
        finally:
            if conn:
                conn.commit()

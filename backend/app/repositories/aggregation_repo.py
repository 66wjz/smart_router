"""
统一聚合实体 Repository - agg_unified 表（CH-023）

一行 = 一个聚合名，用 kind 区分两类语义：
  static：固定成员列表（原 agg_model_group），支持异名成员
  rule  ：手写聚合名（原 agg_aggregated_name），成员由路由规则在运行时匹配

探测字段（probe_enabled / template_id / interval_seconds / slow_threshold_seconds /
sort_mode / schedule）统一存在本表；template_id 非空时模板值优先。
"""

import json

from app.repositories.base import BaseRepository


class AggregationRepository(BaseRepository):
    TABLE = "agg_unified"

    @staticmethod
    def _parse_members(raw) -> list[dict]:
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
                result.append({"upstream": item, "model": None, "weight": 1})
            elif isinstance(item, dict) and item.get("upstream"):
                result.append({
                    "upstream": str(item["upstream"]),
                    "model": str(item["model"]) if item.get("model") else None,
                    "weight": int(item.get("weight", 1) or 1),
                })
        return result

    @staticmethod
    def _parse_bindings(raw) -> list[dict] | None:
        """解析 rule_bindings（CH-024）

        None / 空数组 = 全跟随（所有规则、每条规则的全部候选）
        [{"rule": "默认对话", "candidates": null}]  → 只用该规则，候选全跟随
        [{"rule": "视觉理解", "candidates": [{"upstream","model"}]}] → 显式候选子集
        """
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else None
            except Exception:
                return None
        if not isinstance(raw, list) or not raw:
            return None
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rule_name = str(item.get("rule") or "").strip()
            if not rule_name:
                continue
            cands = item.get("candidates")
            if cands is None:
                result.append({"rule": rule_name, "candidates": None})
                continue
            if not isinstance(cands, list):
                continue
            picked = []
            for c in cands:
                if isinstance(c, dict) and c.get("upstream"):
                    picked.append({
                        "upstream": str(c["upstream"]),
                        "model": str(c["model"]) if c.get("model") else "",
                    })
            result.append({"rule": rule_name, "candidates": picked})
        return result or None

    @staticmethod
    def _parse_schedule(raw) -> dict:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _parse_groups(raw) -> list[str]:
        """解析聚合可用分组（CH-034）

        空 / NULL / 非法 → []（语义：所有 Key 可用，兼容存量）
        """
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else []
            except Exception:
                raw = []
        if not isinstance(raw, list):
            return []
        return [str(g) for g in raw if g]

    def list_all(self) -> dict[str, dict]:
        """{聚合名: {kind, members, rule_bindings, groups, enabled, ...}}；表不存在时返回空"""
        try:
            rows = self.query(
                f"SELECT name, kind, members, rule_bindings, groups, enabled, probe_enabled, template_id, "
                f"sort_mode, interval_seconds, slow_threshold_seconds, schedule, remark "
                f"FROM {self.TABLE} ORDER BY kind, name"
            )
        except Exception:
            return {}
        result = {}
        for r in rows:
            result[r["name"]] = {
                "name": r["name"],
                "kind": r.get("kind") or "static",
                "members": self._parse_members(r.get("members")),
                "rule_bindings": self._parse_bindings(r.get("rule_bindings")),
                "groups": self._parse_groups(r.get("groups")),
                "enabled": bool(r.get("enabled", 1)),
                "probe_enabled": bool(r.get("probe_enabled", 0)),
                "template_id": r.get("template_id"),
                "sort_mode": r.get("sort_mode") or "stable",
                "interval_seconds": r.get("interval_seconds"),
                "slow_threshold_seconds": r.get("slow_threshold_seconds"),
                "schedule": self._parse_schedule(r.get("schedule")),
                "remark": r.get("remark") or "",
            }
        return result

    def upsert(self, name: str, data: dict) -> None:
        """新建或更新一个聚合（未提供的字段保持原值，用 COALESCE 实现部分更新语义）"""
        kind = data.get("kind") or "static"
        members = self._parse_members(data.get("members"))
        bindings = self._parse_bindings(data.get("rule_bindings"))
        groups = self._parse_groups(data.get("groups"))
        schedule = json.dumps(self._parse_schedule(data.get("schedule")), ensure_ascii=False)
        self.execute(
            f"INSERT INTO {self.TABLE} "
            f"(name, kind, members, rule_bindings, groups, enabled, probe_enabled, template_id, sort_mode, "
            f" interval_seconds, slow_threshold_seconds, schedule, remark) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT(name) DO UPDATE SET "
            f"kind = excluded.kind, members = excluded.members, "
            f"rule_bindings = excluded.rule_bindings, groups = excluded.groups, "
            f"enabled = excluded.enabled, "
            f"probe_enabled = excluded.probe_enabled, template_id = excluded.template_id, "
            f"sort_mode = excluded.sort_mode, interval_seconds = excluded.interval_seconds, "
            f"slow_threshold_seconds = excluded.slow_threshold_seconds, "
            f"schedule = excluded.schedule, remark = excluded.remark, "
            f"updated_at = CURRENT_TIMESTAMP",
            (
                name,
                kind,
                json.dumps(members, ensure_ascii=False),
                json.dumps(bindings, ensure_ascii=False) if bindings else None,
                json.dumps(groups, ensure_ascii=False) if groups else None,
                1 if data.get("enabled", True) else 0,
                1 if data.get("probe_enabled") else 0,
                data.get("template_id"),
                data.get("sort_mode") or "stable",
                data.get("interval_seconds"),
                data.get("slow_threshold_seconds"),
                schedule,
                data.get("remark") or "",
            ),
        )

    def list_rule_bindings(self) -> dict[str, list[dict] | None]:
        """所有 rule 聚合的绑定 {聚合名: bindings 或 None}（供规则变更时清理）"""
        try:
            rows = self.query(
                f"SELECT name, rule_bindings FROM {self.TABLE} WHERE kind = 'rule' ORDER BY name"
            )
        except Exception:
            return {}
        return {r["name"]: self._parse_bindings(r.get("rule_bindings")) for r in rows}

    def update_rule_bindings(self, name: str, bindings: list[dict] | None) -> None:
        """只更新绑定字段（规则删除/改名时清理用，不动其他配置）"""
        self.execute(
            f"UPDATE {self.TABLE} SET rule_bindings = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE name = ?",
            (json.dumps(bindings, ensure_ascii=False) if bindings else None, name),
        )

    def delete(self, name: str) -> bool:
        cur = self.execute(f"DELETE FROM {self.TABLE} WHERE name = ?", (name,))
        return cur.rowcount > 0

    def clear_template_refs(self, template_id: int) -> list[str]:
        """模板被删除时：把引用它的聚合 template_id 置空，返回受影响的聚合名"""
        rows = self.query(
            f"SELECT name FROM {self.TABLE} WHERE template_id = ? ORDER BY name", (template_id,)
        )
        names = [r["name"] for r in rows]
        if names:
            self.execute(
                f"UPDATE {self.TABLE} SET template_id = NULL, updated_at = CURRENT_TIMESTAMP "
                f"WHERE template_id = ?",
                (template_id,),
            )
        return names

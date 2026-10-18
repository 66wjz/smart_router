"""
聚合实体与规则绑定（CH-026）

覆盖：聚合组 CRUD、聚合实体读写、探测模板 CRUD、rule 绑定裁剪与清理。
探测配置与计划见 config_probe_plan.py。
"""

import copy
import logging
import os

log = logging.getLogger("router")


class AggregationConfigMixin:
    # ============================================================
    # 同名模型聚合组（CH-019 二期：可查看/可编辑/可控）
    # ============================================================

    def get_model_groups(self) -> dict[str, dict]:
        """人工配置的同名聚合组 {model: {upstreams, enabled}}"""
        with self._lock:
            return copy.deepcopy(self._model_groups)

    def save_model_group(self, model: str, upstreams: list[dict], enabled: bool = True) -> None:
        """保存 static 聚合（写入统一表，保留已有探测配置）"""
        existing = self._aggregations.get(model) or {}
        self._repos["aggregation"].upsert(model, {
            "kind": "static",
            "members": upstreams,
            "rule_bindings": None,
            "enabled": enabled,
            "probe_enabled": existing.get("probe_enabled", False),
            "template_id": existing.get("template_id"),
            "sort_mode": existing.get("sort_mode", "stable"),
            "interval_seconds": existing.get("interval_seconds"),
            "slow_threshold_seconds": existing.get("slow_threshold_seconds"),
            "schedule": existing.get("schedule") or {},
            "remark": existing.get("remark") or "",
        })
        self._refresh_unified()

    def delete_model_group(self, model: str) -> None:
        """删除人工配置 → 该模型回到自动发现"""
        self._repos["aggregation"].delete(model)
        self._refresh_unified()

    def discover_model_sources(self, model_name: str) -> list[str]:
        """自动发现同名来源（忽略人工配置），供聚合页展示"自动发现"基线"""
        found: list[str] = []
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            if not self.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                if isinstance(m, dict) and m.get("name") == model_name:
                    found.append(uid)
                    break
        return found

    # ============================================================
    # 统一聚合实体 + 探测模板（CH-023）
    # ============================================================

    def sync_unified_tables(self) -> None:
        """执行增量 SQL（幂等建表 + 迁移），供启动时补齐 CH-023 / CH-024 结构"""
        import os
        from app.core.database import get_conn

        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        for filename in (
            "07_增量_20261017_聚合统一与探测模板.sql",
            "08_增量_20261017_聚合规则绑定.sql",
        ):
            path = os.path.join(base, "sql", "increment", filename)
            with open(path, encoding="utf-8") as f:
                try:
                    get_conn().executescript(f.read())
                except Exception as e:
                    # 08 的 ALTER TABLE 重复执行会报 duplicate column，视为已补
                    if "duplicate column" not in str(e).lower():
                        raise

    def _refresh_unified(self) -> None:
        """只重载统一聚合/模板视图（不动 Key 池与上游缓存），供聚合 CRUD 后热更新"""
        with self._lock:
            self._aggregations = self._repos["aggregation"].list_all()
            self._probe_templates = self._repos["probe_template"].list_all()
            self._sync_legacy_views()

    def get_aggregations(self) -> dict[str, dict]:
        with self._lock:
            return copy.deepcopy(self._aggregations)

    def get_probe_templates(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._probe_templates)

    def save_aggregation(self, name: str, data: dict) -> None:
        """保存聚合（新建/更新）并刷新内存视图"""
        self._repos["aggregation"].upsert(name, data)
        self._refresh_unified()

    def delete_aggregation(self, name: str) -> bool:
        """删除聚合。

        CH-033：自动发现的同名聚合在 agg_unified 里没有行（由 collect_group_members()
        即时推导），直接 DELETE 会删不到东西。此时改为落库一条 enabled=false 的
        static 行，语义是「关闭该聚合」——既满足移除意图，又可逆（恢复自动 = 改回 true）。
        """
        if self._repos["aggregation"].delete(name):
            self._refresh_unified()
            return True
        if name not in self.collect_group_members():
            return False
        # 自动发现聚合：落库关闭，避免它继续出现在列表与路由候选里
        self._repos["aggregation"].upsert(name, {
            "kind": "static",
            "members": [],
            "rule_bindings": None,
            "enabled": False,
            "probe_enabled": False,
            "template_id": None,
            "sort_mode": "stable",
            "interval_seconds": None,
            "slow_threshold_seconds": None,
            "schedule": {},
            "remark": "已关闭（原自动发现聚合）",
        })
        self._refresh_unified()
        return True

    def save_probe_template(self, data: dict, template_id: int | None = None) -> int:
        """新建或更新探测模板；返回模板 id"""
        if template_id:
            self._repos["probe_template"].update(template_id, data)
            tid = template_id
        else:
            tid = self._repos["probe_template"].create(data)
        self._refresh_unified()
        return tid

    def delete_probe_template(self, template_id: int) -> list[str]:
        """删除模板：引用它的聚合 template_id 置空（回退自配 → 全局），返回受影响聚合名"""
        affected = self._repos["aggregation"].clear_template_refs(template_id)
        self._repos["probe_template"].delete(template_id)
        self._refresh_unified()
        return affected

    def rule_bindings_of(self, name: str) -> list[dict] | None:
        """某 rule 聚合的规则绑定（CH-024）；None = 全跟随"""
        with self._lock:
            entity = self._aggregations.get(name)
        if not entity or entity.get("kind") != "rule":
            return None
        return entity.get("rule_bindings")

    def bound_rules(self, name: str | None = None) -> list[dict]:
        """按聚合绑定裁剪后的规则列表 [{name, match, candidates}]

        name 为空、聚合无绑定、或绑定里的规则都已失效 → 返回全部规则（兼容旧行为）。
        """
        bindings = self.rule_bindings_of(name) if name else None
        if not bindings:
            return list(self._rules)

        by_name = {r.get("name"): r for r in self._rules}
        result: list[dict] = []
        for b in bindings:
            rule = by_name.get(b.get("rule"))
            if rule is None:
                continue
            picked = b.get("candidates")
            if picked is None:
                result.append(rule)
                continue
            wanted = {(c.get("upstream"), c.get("model")) for c in picked}
            cands = [
                c for c in rule.get("candidates", [])
                if (c.get("upstream", self.default_upstream), c.get("model")) in wanted
            ]
            if cands:
                result.append({**rule, "candidates": cands})
        return result or list(self._rules)

    def prune_rule_bindings(self, valid_names: set[str]) -> list[str]:
        """规则被删除/改名后清理各 rule 聚合的绑定（CH-024）

        返回受影响聚合名。清理后若绑定为空 → 存 NULL（回退全跟随）。
        """
        affected: list[str] = []
        repo = self._repos["aggregation"]
        for name, bindings in repo.list_rule_bindings().items():
            if not bindings:
                continue
            kept = [b for b in bindings if b.get("rule") in valid_names]
            if len(kept) == len(bindings):
                continue
            repo.update_rule_bindings(name, kept or None)
            affected.append(name)
        if affected:
            self._refresh_unified()
            log.warning(f"[聚合] 规则变更后清理了 {len(affected)} 个聚合的绑定: {affected}")
        return affected

    def rule_binding_issues(self, name: str) -> list[dict]:
        """检查某 rule 聚合的绑定是否有失效项（规则不存在 / 候选已被移除）"""
        bindings = self.rule_bindings_of(name) or []
        by_name = {r.get("name"): r for r in self._rules}
        issues: list[dict] = []
        for b in bindings:
            rule = by_name.get(b.get("rule"))
            if rule is None:
                issues.append({"rule": b.get("rule"), "reason": "rule_missing"})
                continue
            picked = b.get("candidates")
            if picked is None:
                continue
            existing = {(c.get("upstream"), c.get("model")) for c in rule.get("candidates", [])}
            for c in picked:
                if (c.get("upstream"), c.get("model")) not in existing:
                    issues.append({
                        "rule": b.get("rule"),
                        "reason": "candidate_missing",
                        "candidate": c,
                    })
        return issues

    def is_rule_aggregation(self, name: str) -> bool:
        """是否为 rule 类型聚合（候选来自路由规则）"""
        with self._lock:
            entity = self._aggregations.get(name)
        return bool(entity and entity.get("kind") == "rule")

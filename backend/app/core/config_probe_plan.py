"""
聚合探测配置与探测计划（CH-026 从 config_aggregation.py 拆出）

覆盖：探测配置 CRUD、模板解析优先级、探测单元去重、排班计划计算。
聚合实体与规则绑定见 config_aggregation.py。
"""

import copy
import logging

from app.core.probe_schedule import is_active as schedule_is_active

log = logging.getLogger("router")


class ProbePlanConfigMixin:
    # ============================================================
    # 聚合组探测配置（CH-021）
    # ============================================================

    def get_probe_configs(self) -> dict[str, dict]:
        """全部聚合组的探测配置 {聚合名: {...}}"""
        with self._lock:
            return copy.deepcopy(self._probe_configs)

    def sync_probe_config_table(self) -> None:
        """建表（幂等），供启动时补齐增量表"""
        self._repos["probe_config"].execute(
            "CREATE TABLE IF NOT EXISTS agg_probe_config ("
            "model TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, "
            "interval_seconds INTEGER, slow_threshold_seconds REAL, "
            "sort_mode TEXT NOT NULL DEFAULT 'stable', "
            "schedule TEXT NOT NULL DEFAULT '{}', "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

    def save_probe_config(self, model: str, data: dict) -> None:
        """保存某聚合的探测策略（CH-023 写入统一表；自动发现的组仍写旧表）"""
        existing = self._aggregations.get(model)
        if existing is not None:
            self._repos["aggregation"].upsert(model, {
                "kind": existing.get("kind") or "static",
                "members": existing.get("members") or [],
                "rule_bindings": existing.get("rule_bindings"),
                "enabled": existing.get("enabled", True),
                "probe_enabled": bool(data.get("enabled")),
                "template_id": data.get("template_id", existing.get("template_id")),
                "sort_mode": data.get("sort_mode") or "stable",
                "interval_seconds": data.get("interval_seconds"),
                "slow_threshold_seconds": data.get("slow_threshold_seconds"),
                "schedule": data.get("schedule") or {},
                "remark": existing.get("remark") or "",
            })
        self._repos["probe_config"].upsert(model, data)
        self._refresh_unified()
        with self._lock:
            self._probe_configs = self._repos["probe_config"].list_all()

    def delete_probe_config(self, model: str) -> None:
        """关闭某聚合的定时探测（该组回到"不探测"，全局探测不受影响）"""
        existing = self._aggregations.get(model)
        if existing is not None:
            self._repos["aggregation"].upsert(model, {
                "kind": existing.get("kind") or "static",
                "members": existing.get("members") or [],
                "rule_bindings": existing.get("rule_bindings"),
                "enabled": existing.get("enabled", True),
                "probe_enabled": False,
                "template_id": None,
                "sort_mode": "stable",
                "interval_seconds": None,
                "slow_threshold_seconds": None,
                "schedule": {},
                "remark": existing.get("remark") or "",
            })
        self._repos["probe_config"].delete(model)
        self._refresh_unified()
        with self._lock:
            self._probe_configs = self._repos["probe_config"].list_all()

    def group_probe_settings(self, group_name: str) -> dict:
        """某聚合的生效探测参数（CH-023）

        优先级：探测模板（若挂）→ 聚合自配 → 全局 latency_probe → 内置默认。
        挂模板时模板的 interval/slow/sort/schedule 全部生效，聚合自配字段被忽略。
        """
        global_cfg = self.probe_config
        entity = self._aggregations.get(group_name)
        if entity is not None:
            conf = {
                "enabled": bool(entity.get("probe_enabled")),
                "interval_seconds": entity.get("interval_seconds"),
                "slow_threshold_seconds": entity.get("slow_threshold_seconds"),
                "sort_mode": entity.get("sort_mode"),
                "schedule": entity.get("schedule"),
            }
            configured = bool(entity.get("probe_enabled") or entity.get("template_id")
                              or entity.get("interval_seconds") or entity.get("schedule"))
        else:
            conf = self._probe_configs.get(group_name) or {}
            configured = bool(conf)

        template = self._template_of(entity) if entity is not None else None
        if template is not None:
            return {
                "enabled": bool(conf.get("enabled", False)),
                "interval_seconds": template.get("interval_seconds")
                or global_cfg.get("interval_seconds", 120),
                "slow_threshold_seconds": template.get("slow_threshold_seconds")
                if template.get("slow_threshold_seconds") is not None
                else global_cfg.get("slow_threshold_seconds", 10),
                "sort_mode": template.get("sort_mode") or "stable",
                "schedule": template.get("schedule") or global_cfg.get("schedule") or {"mode": "always"},
                "configured": True,
                "template_id": template.get("id"),
                "template_name": template.get("name", ""),
            }

        return {
            "enabled": bool(conf.get("enabled", False)),
            "interval_seconds": conf.get("interval_seconds") or global_cfg.get("interval_seconds", 120),
            "slow_threshold_seconds": conf.get("slow_threshold_seconds")
            if conf.get("slow_threshold_seconds") is not None
            else global_cfg.get("slow_threshold_seconds", 10),
            "sort_mode": conf.get("sort_mode") or "stable",
            "schedule": conf.get("schedule") or global_cfg.get("schedule") or {"mode": "always"},
            "configured": configured,
            "template_id": None,
            "template_name": "",
        }

    def _template_of(self, entity: dict | None) -> dict | None:
        """取聚合挂载的探测模板（未挂或模板已删除时返回 None）"""
        if not entity:
            return None
        tid = entity.get("template_id")
        if tid is None:
            return None
        for t in self._probe_templates:
            if t.get("id") == tid:
                return t
        return None

    def rule_candidate_units(self, aggregation: str | None = None) -> list[dict]:
        """规则候选展开后的 (上游源, 真实模型) 列表（CH-023 / CH-024）

        传 aggregation 时只展开该聚合绑定的规则与候选；不传则展开全部规则。
        聚合名形式的候选会继续展开为各源真实模型名。
        """
        group_members = self.collect_group_members()
        units: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for rule in self.bound_rules(aggregation):
            for c in rule.get("candidates", []):
                model = c.get("model", "")
                expanded = (
                    [(m["upstream"], m["model"]) for m in group_members[model]]
                    if model in group_members
                    else [(c.get("upstream", self.default_upstream), model)]
                )
                for uid, actual in expanded:
                    if not uid or not actual or (uid, actual) in seen:
                        continue
                    seen.add((uid, actual))
                    units.append({"upstream": uid, "model": actual})
        return units

    def collect_group_members(self) -> dict[str, list[dict]]:
        """所有聚合组及其成员（人工配置优先，否则同名自动发现）
        返回 {聚合名: [{upstream, model}]}，model 为该源真实模型名（支持异名）"""
        discovered: dict[str, list[str]] = {}
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            if not self.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                name = m.get("name") if isinstance(m, dict) else str(m)
                if not name or not self.is_model_enabled(uid, name):
                    continue
                discovered.setdefault(name, []).append(uid)

        result: dict[str, list[dict]] = {}
        for name in set(discovered) | set(self._model_groups):
            conf = self._model_groups.get(name)
            if conf is not None:
                if not conf.get("enabled", True):
                    continue  # 聚合关闭 → 不构成聚合组
                members = []
                seen = set()
                for item in conf.get("upstreams", []):
                    uid = item.get("upstream", "")
                    actual = item.get("model") or name
                    if not uid or (uid, actual) in seen:
                        continue
                    if not self.is_upstream_enabled(uid) or not self.is_model_enabled(uid, actual):
                        continue
                    seen.add((uid, actual))
                    members.append({"upstream": uid, "model": actual})
                result[name] = members
            else:
                auto = discovered.get(name, [])
                if len(auto) >= 2:
                    result[name] = [{"upstream": uid, "model": name} for uid in auto]
        return result

    def is_model_group(self, name: str) -> bool:
        """是否为聚合组名（轻量判断，供请求路径使用）
        人工配置且启用 → 是；否则同名模型分布在 >=2 个启用的上游源 → 是"""
        conf = self._model_groups.get(name)
        if conf is not None:
            return bool(conf.get("enabled", True))
        count = 0
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            if not self.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                if isinstance(m, dict) and m.get("name") == name:
                    count += 1
                    break
            if count >= 2:
                return True
        return False

    def collect_probe_plan(self) -> dict[str, dict]:
        """全局去重后的探测计划（CH-021 / CH-023）

        单元 = (上游源, 该源真实模型名)，全局唯一；聚合只"引用"单元，不拥有。
        返回 {f"{upstream}:{model}": {upstream, model, interval, groups, sources, schedule}}
        多个启用探测的聚合引用同一单元时，间隔取最小值（最严格的组决定新鲜度）。

        CH-023：rule 聚合也纳入计划——其探测对象是「所有规则候选的并集」，
        并在单元上记录 groups，便于排班表看出某单元是被谁拉起来的。
        """
        global_cfg = self.probe_config
        global_interval = global_cfg.get("interval_seconds", 120)
        global_enabled = bool(global_cfg.get("enabled", True))

        plan: dict[str, dict] = {}

        def add(upstream_id: str, model: str, source: str, group: str | None = None,
                interval: int | None = None, schedule: dict | None = None) -> None:
            if not upstream_id or not model:
                return
            key = f"{upstream_id}:{model}"
            entry = plan.get(key)
            if entry is None:
                plan[key] = {
                    "upstream": upstream_id,
                    "model": model,
                    "interval": interval or global_interval,
                    "groups": [group] if group else [],
                    "sources": [source],
                    "schedules": [schedule] if schedule else [],
                }
                return
            if group and group not in entry["groups"]:
                entry["groups"].append(group)
            if source not in entry["sources"]:
                entry["sources"].append(source)
            if schedule and schedule not in entry["schedules"]:
                entry["schedules"].append(schedule)
            if interval:
                entry["interval"] = min(entry["interval"], interval)

        # 1) static 聚合组成员（含自动发现的同名聚合）
        for group_name, members in self.collect_group_members().items():
            settings = self.group_probe_settings(group_name)
            if not settings["enabled"]:
                continue
            for m in members:
                add(m["upstream"], m["model"], "group", group_name,
                    settings["interval_seconds"], settings["schedule"])

        # 2) rule 聚合：候选并集，按该聚合自己的探测配置计入
        for name, entity in self._aggregations.items():
            if entity.get("kind") != "rule" or not entity.get("enabled", True):
                continue
            settings = self.group_probe_settings(name)
            if not settings["enabled"]:
                continue
            for unit in self.rule_candidate_units(name):
                add(unit["upstream"], unit["model"], "group", name,
                    settings["interval_seconds"], settings["schedule"])

        # 3) 路由规则候选 + 4) 别名目标（受全局开关注册）
        #    若规则/别名引用的是聚合名，必须展开成各源的真实模型名，
        #    否则会产生 "源:聚合名" 这种不存在的探测单元（CH-022 修复）
        if global_enabled:
            for unit in self.rule_candidate_units():
                add(unit["upstream"], unit["model"], "rule")
            group_members = self.collect_group_members()
            for p in self._pointers:
                target = p.get("target_model", "")
                if target in group_members:
                    for m in group_members[target]:
                        add(m["upstream"], m["model"], "pointer")
                else:
                    for uid in self.collect_model_upstreams(target):
                        add(uid, target, "pointer")

        # 过滤：上游禁用 / 探测禁用 / 模型级禁用
        for key in list(plan.keys()):
            item = plan[key]
            uid = item["upstream"]
            if not self.is_upstream_enabled(uid) or not self.is_upstream_probe_enabled(uid):
                del plan[key]
                continue
            if not self.is_model_enabled(uid, item["model"]):
                del plan[key]
        return plan

    def probe_plan_active(self, item: dict) -> bool:
        """该探测单元当前是否允许探测

        单元被多个"启用探测的聚合"引用时，任一组处于探测时段即探测（并集语义）；
        若只有规则/别名引用，则看全局 schedule。
        """
        for group_name in item.get("groups") or []:
            if schedule_is_active(self.group_probe_settings(group_name)["schedule"]):
                return True
        if item.get("groups"):
            return False  # 只被聚合引用，且这些聚合当前都在时段外
        return schedule_is_active(self.probe_config.get("schedule"))

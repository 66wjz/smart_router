"""
配置服务 - 所有配置 CRUD 的统一入口
（上游源/规则/密钥/别名/聚合名/系统参数/热重载）
"""

import json

from fastapi import HTTPException

from app.core.config import AppConfig


class ConfigService:
    def __init__(self, config: AppConfig):
        self.config = config

    # ---------- 上游源 ----------

    def list_upstreams(self) -> list[dict]:
        """返回上游源列表（密钥脱敏，附 Key 池数量与完整 Key 供编辑回显）"""
        result = []
        for u in self.config.upstreams:
            uid = u.get("upstream_id", "")
            key = u.get("api_key", "")
            masked = self._mask_key(key)
            result.append({
                "id": uid,
                "name": u.get("name", ""),
                "base_url": u.get("base_url", ""),
                "api_key": masked,
                "key_count": self.config.get_key_count(uid),
                "keys": self.config.get_upstream_all_keys(uid),
                "format": u.get("format", "openai"),
                "group": u.get("group_name", "free"),
                "groups": u.get("groups") or [u.get("group_name", "free")],
                "probe_enabled": bool(u.get("probe_enabled", True)),
                "smart_retry": bool(u.get("smart_retry", False)),
                "enabled": bool(u.get("enabled", True)),
                "models": u.get("models") or [],
            })
        return result

    @staticmethod
    def _mask_key(key: str) -> str:
        if len(key) > 8:
            return key[:4] + "*" * (len(key) - 8) + key[-4:]
        return "****"

    def add_upstream(self, data: dict) -> None:
        if not self.config.add_upstream(data):
            raise HTTPException(400, "上游源 ID 已存在")

    def update_upstream(self, upstream_id: str, data: dict) -> None:
        if not self.config.update_upstream(upstream_id, data):
            raise HTTPException(404, "上游源不存在")

    def delete_upstream(self, upstream_id: str) -> None:
        if not self.config.delete_upstream(upstream_id):
            raise HTTPException(404, "上游源不存在")

    # ---------- 路由规则 ----------

    def get_rules(self) -> list[dict]:
        return self.config.rules

    def set_rules(self, rules: list) -> list[str]:
        return self.config.set_rules(rules)

    # ---------- API Key ----------

    def list_api_keys(self) -> list[dict]:
        """返回 API Key 列表（含完整 key 与脱敏 key）"""
        result = []
        for ak in self.config.api_keys:
            key_val = ak.get("key_value", "")
            result.append({
                "name": ak.get("name", ""),
                "key": key_val,
                "key_masked": self._mask_key(key_val),
                "enabled": bool(ak.get("enabled", True)),
                "groups": self._parse_groups(ak.get("groups")),
            })
        return result

    @staticmethod
    def _parse_groups(groups_raw) -> list[str]:
        if isinstance(groups_raw, list):
            return groups_raw
        try:
            parsed = json.loads(groups_raw) if groups_raw else ["free"]
            return parsed if isinstance(parsed, list) else ["free"]
        except Exception:
            return ["free"]

    def add_api_key(self, data: dict) -> None:
        name = data.get("name", "")
        key = data.get("key", "")
        groups = data.get("groups", ["free"])
        enabled = data.get("enabled", True)
        if not key:
            raise HTTPException(400, "key 为必填")
        if not self.config.add_api_key(name, key, groups, enabled):
            raise HTTPException(400, "API Key 已存在")

    def update_api_key(self, key_value: str, data: dict) -> None:
        if not self.config.update_api_key(
            key_value,
            name=data.get("name"),
            groups=data.get("groups"),
            enabled=data.get("enabled"),
        ):
            raise HTTPException(404, "API Key 不存在")

    def delete_api_key(self, key_value: str) -> None:
        if not self.config.delete_api_key(key_value):
            raise HTTPException(404, "API Key 不存在")

    # ---------- 模型别名 ----------

    def list_pointers(self) -> list[dict]:
        return self.config.model_pointers

    def add_pointer(self, data: dict) -> None:
        name = data.get("name", "")
        target = data.get("target_model", "")
        upstream = data.get("upstream") or self.config.default_upstream
        if not name or not target:
            raise HTTPException(400, "name 和 target_model 为必填")
        if not self.config.add_model_pointer(name, target, upstream):
            raise HTTPException(400, f"别名 '{name}' 已存在")

    def update_pointer(self, name: str, data: dict) -> None:
        if not self.config.update_model_pointer(
            name,
            target_model=data.get("target_model"),
            upstream_id=data.get("upstream"),
        ):
            raise HTTPException(404, f"别名 '{name}' 不存在")

    def delete_pointer(self, name: str) -> None:
        if not self.config.delete_model_pointer(name):
            raise HTTPException(404, f"别名 '{name}' 不存在")

    # ---------- 聚合模型名 ----------

    def get_aggregated_names(self) -> list[str]:
        return list(self.config.aggregated_names)

    def set_aggregated_names(self, names: list[str]) -> None:
        self.config.set_aggregated_names(names)

    # ---------- 同名模型聚合组（CH-019 二期） ----------

    def list_model_groups(self) -> list[dict]:
        """列出所有聚合组：自动发现结果 + 人工配置（若有）
        - 自动发现：只返回同名且分布在 >=2 个源的模型
        - 人工配置：始终返回（含异名成员），即使只剩 1 个源
        每项：{model(聚合名), sources, members, enabled, configured, auto_sources}
        - sources: 生效的上游源顺序（兼容旧前端）
        - members: [{upstream, model}]，model 为该源真实模型名（支持异名）
        """
        configured = self.config.get_model_groups()

        # 聚合名 → 自动发现的可用源（严格同名）
        discovered: dict[str, list[str]] = {}
        for u in self.config.upstreams:
            uid = u.get("upstream_id", "")
            if not self.config.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                name = m.get("name") if isinstance(m, dict) else str(m)
                if not name or not self.config.is_model_enabled(uid, name):
                    continue
                discovered.setdefault(name, []).append(uid)

        names = set(discovered) | set(configured)
        groups = []
        for name in sorted(names):
            auto_sources = discovered.get(name, [])
            conf = configured.get(name)
            if conf is None and len(auto_sources) < 2:
                continue  # 未人工配置且只有单源 → 不是聚合组，不展示
            if conf is not None:
                members = [
                    {"upstream": s["upstream"], "model": s.get("model") or name}
                    for s in conf.get("upstreams", [])
                ]
                enabled = bool(conf.get("enabled", True))
            else:
                members = [{"upstream": uid, "model": name} for uid in auto_sources]
                enabled = True
            groups.append({
                "model": name,
                "sources": [m["upstream"] for m in members],
                "members": members,
                "enabled": enabled,
                "configured": conf is not None,
                "auto_sources": auto_sources,
            })
        return groups

    def save_model_group(self, model: str, upstreams: list[dict], enabled: bool = True) -> None:
        self.config.save_model_group(model, upstreams, enabled)

    def delete_model_group(self, model: str) -> None:
        self.config.delete_model_group(model)

    # ---------- 聚合组探测配置（CH-021） ----------

    def save_group_probe(self, model: str, data: dict) -> None:
        self.config.save_probe_config(model, data)

    def get_probe_plan(self, probe=None) -> dict:
        """全局去重探测计划 + 汇总（含探测成本估算与排班信息，CH-023）"""
        plan = self.config.collect_probe_plan()
        members = self.config.collect_group_members()
        total_members = sum(len(v) for v in members.values())
        panel = probe.get_panel() if probe is not None else {}
        entities = self.config.get_aggregations()
        daily = 0
        units = []
        for key, item in plan.items():
            try:
                daily += int(86400 / max(1, item["interval"]))
            except (TypeError, ValueError):
                pass
            uid = item["upstream"]
            upstream = self.config.get_upstream(uid) or {}
            live = (probe.data.get(key) if probe is not None else None) or {}
            groups = item["groups"]
            # 该单元被哪些聚合拉起：取各引用聚合的生效定时段（并集语义已在 probe_plan_active 中体现）
            schedules = []
            for gname in groups:
                sched = self.config.group_probe_settings(gname)["schedule"]
                if sched and sched not in schedules:
                    schedules.append(sched)
            units.append({
                "key": key,
                "upstream": uid,
                "upstream_name": upstream.get("name", uid),
                "model": item["model"],
                "groups": groups,
                "group_kinds": {
                    g: (entities.get(g, {}).get("kind") or "static") for g in groups
                },
                "sources": item["sources"],
                "interval": item["interval"],
                "schedule": schedules[0] if len(schedules) == 1 else {"mode": "always"},
                "schedules": schedules,
                "latency": live.get("latency"),
                "status": live.get("status", "unknown"),
                "last_check": live.get("last_check", 0),
                "stale": bool(panel.get(key, {}).get("stale")),
                "active_now": self.config.probe_plan_active(item),
            })
        units.sort(key=lambda u: (u["upstream"], u["model"]))
        return {
            "summary": {
                "unit_count": len(plan),
                "member_refs": total_members,
                "dedup_saved": max(0, total_members - len(plan)),
                "daily_requests": daily,
                "global_interval": self.config.probe_config.get("interval_seconds", 120),
                "aggregation_count": len(entities),
            },
            "units": units,
        }

    def list_probe_configs(self) -> dict:
        """各聚合的探测配置 + 生效值（供聚合页展示，CH-023 含 rule 聚合）"""
        configs = self.config.get_probe_configs()
        members = self.config.collect_group_members()
        aggregations = self.config.get_aggregations()
        templates = {t["id"]: t for t in self.config.get_probe_templates()}
        result = {}
        for name in set(configs) | set(members) | set(aggregations):
            entity = aggregations.get(name) or {}
            settings = self.config.group_probe_settings(name)
            member_count = (
                len(self.config.rule_candidate_units())
                if entity.get("kind") == "rule"
                else len(members.get(name) or [])
            )
            result[name] = {
                "model": name,
                "kind": entity.get("kind") or "static",
                "configured": settings["configured"],
                "enabled": settings["enabled"],
                "interval_seconds": settings["interval_seconds"],
                "slow_threshold_seconds": settings["slow_threshold_seconds"],
                "sort_mode": settings["sort_mode"],
                "schedule": settings["schedule"],
                "template_id": settings.get("template_id"),
                "template_name": settings.get("template_name", ""),
                "template_exists": settings.get("template_id") in templates
                if settings.get("template_id") else False,
                "member_count": member_count,
                "raw": {
                    "enabled": bool(entity.get("probe_enabled")) if entity else bool(configs.get(name)),
                    "interval_seconds": entity.get("interval_seconds")
                    if entity else (configs.get(name) or {}).get("interval_seconds"),
                    "slow_threshold_seconds": entity.get("slow_threshold_seconds")
                    if entity else (configs.get(name) or {}).get("slow_threshold_seconds"),
                    "sort_mode": (entity.get("sort_mode") if entity else None)
                    or (configs.get(name) or {}).get("sort_mode") or "stable",
                    "schedule": (entity.get("schedule") if entity else None)
                    or (configs.get(name) or {}).get("schedule") or {},
                    "template_id": entity.get("template_id") if entity else None,
                },
            }
        return result

    # ---------- 统一聚合实体（CH-023） ----------

    def list_aggregations(self) -> list[dict]:
        """统一聚合列表：static（固定成员）+ rule（规则匹配），含生效探测参数与模板名

        额外并入「自动发现的同名聚合」（未人工配置、同名模型分布在 >=2 个源），
        让升级后这类聚合仍在页面上可见可配，configured=false 标识其为自动发现。
        CH-024：rule 聚合额外返回 rule_bindings / rule_binding_summary / stale_bindings。
        """
        entities = self.config.get_aggregations()
        templates = {t["id"]: t for t in self.config.get_probe_templates()}
        rules_by_name = {r.get("name"): r for r in self.config.rules}

        result = []
        for name, entity in sorted(entities.items(), key=lambda kv: (kv[1].get("kind") != "static", kv[0])):
            # CH-033：自动发现聚合被「移除」后会落一条 enabled=false + 空成员的 static 行，
            # 它没有任何实际配置（正常的关闭聚合一定保留成员），不应再出现在列表里。
            if (entity.get("kind") == "static" and not entity.get("enabled", True)
                    and not (entity.get("members") or [])):
                continue
            kind = entity.get("kind") or "static"
            settings = self.config.group_probe_settings(name)
            item = {
                "name": name,
                "kind": kind,
                "enabled": bool(entity.get("enabled", True)),
                "members": entity.get("members") or [],
                "configured": True,
                "template_id": entity.get("template_id"),
                "template_name": templates.get(entity.get("template_id"), {}).get("name", ""),
                "probe": {
                    "enabled": settings["enabled"],
                    "interval_seconds": settings["interval_seconds"],
                    "slow_threshold_seconds": settings["slow_threshold_seconds"],
                    "sort_mode": settings["sort_mode"],
                    "schedule": settings["schedule"],
                    "template_id": settings.get("template_id"),
                    "template_name": settings.get("template_name", ""),
                },
                "self_config": {
                    "probe_enabled": bool(entity.get("probe_enabled")),
                    "interval_seconds": entity.get("interval_seconds"),
                    "slow_threshold_seconds": entity.get("slow_threshold_seconds"),
                    "sort_mode": entity.get("sort_mode") or "stable",
                    "schedule": entity.get("schedule") or {},
                },
                "remark": entity.get("remark") or "",
            }
            if kind == "rule":
                bindings = entity.get("rule_bindings")
                units = self.config.rule_candidate_units(name)
                item["rule_bindings"] = bindings
                item["member_count"] = len(units)
                item["rule_names"] = [b["rule"] for b in (bindings or [])] or [
                    r.get("name", "") for r in self.config.rules
                    if any(c.get("model") for c in r.get("candidates", []))
                ]
                item["rule_binding_summary"] = self._binding_summary(bindings, rules_by_name)
                item["stale_bindings"] = self.config.rule_binding_issues(name)
            else:
                item["rule_bindings"] = None
                item["member_count"] = len(item["members"])
                item["rule_binding_summary"] = None
                item["stale_bindings"] = []
            result.append(item)

        # 自动发现但未落库的同名聚合（configured=false，探测参数取全局/旧表）
        auto_members = self.config.collect_group_members()
        for name, members in sorted(auto_members.items()):
            if name in entities:
                continue
            settings = self.config.group_probe_settings(name)
            result.append({
                "name": name,
                "kind": "static",
                "enabled": True,
                "members": members,
                "configured": False,
                "template_id": None,
                "template_name": "",
                "probe": {
                    "enabled": settings["enabled"],
                    "interval_seconds": settings["interval_seconds"],
                    "slow_threshold_seconds": settings["slow_threshold_seconds"],
                    "sort_mode": settings["sort_mode"],
                    "schedule": settings["schedule"],
                    "template_id": None,
                    "template_name": "",
                },
                "self_config": {
                    "probe_enabled": settings["enabled"],
                    "interval_seconds": settings["interval_seconds"],
                    "slow_threshold_seconds": None,
                    "sort_mode": "stable",
                    "schedule": {},
                },
                "remark": "",
                "member_count": len(members),
            })

        # CH-028：按人工排序重排（空数组 = 保持上面的默认顺序）
        order = self.config.aggregation_order
        if order:
            rank = {name: i for i, name in enumerate(order)}
            result.sort(key=lambda it: rank.get(it["name"], len(rank)))
        return result

    @staticmethod
    def _binding_summary(bindings: list[dict] | None, rules_by_name: dict) -> dict | None:
        """绑定的可读摘要：规则数 / 候选数 / 每条规则选了几个（CH-024）"""
        if not bindings:
            return None
        items = []
        cand_total = 0
        for b in bindings:
            rule = rules_by_name.get(b.get("rule")) or {}
            picked = b.get("candidates")
            if picked is None:
                count = len(rule.get("candidates", []))
                followed = True
            else:
                count = len(picked)
                followed = False
            cand_total += count
            items.append({"rule": b.get("rule"), "count": count, "follow_all": followed})
        return {"rule_count": len(bindings), "candidate_count": cand_total, "items": items}

    def save_aggregation(self, name: str, data: dict) -> None:
        self.config.save_aggregation(name, data)

    def delete_aggregation(self, name: str) -> None:
        if not self.config.delete_aggregation(name):
            raise HTTPException(404, f"聚合 {name} 不存在")

    def save_aggregation_order(self, names: list[str]) -> int:
        """保存聚合列表人工顺序（CH-028）；只保留当前真实存在的聚合名"""
        existing = set(self.config.get_aggregations())
        # 自动发现的聚合不在 agg_unified 里，但也要能排，故并入
        existing |= set(self.config.collect_group_members())
        cleaned = [n for n in (names or []) if n in existing]
        self.config.set_aggregation_order(cleaned)
        return len(cleaned)


    # ---------- 探测模板（CH-023） ----------

    def list_probe_templates(self) -> list[dict]:
        """模板列表 + 被引用次数与引用方名字"""
        entities = self.config.get_aggregations()
        templates = self.config.get_probe_templates()
        refs: dict[int, list[str]] = {}
        for name, entity in entities.items():
            tid = entity.get("template_id")
            if tid is not None:
                refs.setdefault(tid, []).append(name)
        for t in templates:
            t["ref_count"] = len(refs.get(t["id"], []))
            t["ref_names"] = sorted(refs.get(t["id"], []))
        return templates

    def save_probe_template(self, data: dict, template_id: int | None = None) -> int:
        return self.config.save_probe_template(data, template_id)

    def delete_probe_template(self, template_id: int) -> list[str]:
        return self.config.delete_probe_template(template_id)

    # ---------- 系统参数 ----------

    def get_probe_config(self) -> dict:
        return self.config.probe_config

    def set_probe_config(self, data: dict) -> None:
        self.config.set_probe_config(data)

    def get_retry_config(self) -> dict:
        return self.config.retry_config

    def set_retry_config(self, data: dict) -> None:
        self.config.set_retry_config(data)

    def get_smart_retry_config(self) -> dict:
        return self.config.smart_retry_config

    def set_smart_retry_config(self, data: dict) -> None:
        self.config.set_smart_retry_config(data)

    def get_failover_config(self) -> dict:
        return self.config.failover_config

    def set_failover_config(self, data: dict) -> None:
        self.config.set_failover_config(data)

    # ---------- 分组管理 ----------

    def get_groups(self) -> list[dict]:
        return self.config.get_groups()

    def set_groups(self, groups: list[dict]) -> None:
        self.config.set_groups(groups)

    # ---------- 热重载 ----------

    def reload(self) -> None:
        self.config.reload()

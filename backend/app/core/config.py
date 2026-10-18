"""
配置仓库 - 内存缓存 + SQLite 持久化 + 热重载
替代 v4 的 core/config.py（YAML 存储改为数据库存储）。
提供与 v4 兼容的属性和方法接口，供路由引擎/探测/健康模块使用。
"""

import copy
import logging
import threading

from app.core.key_pool import KeyPool
from app.core.probe_schedule import is_active as schedule_is_active
from app.repositories import (
    AggregatedNameRepository,
    AggregationRepository,
    ApiKeyRepository,
    ModelGroupRepository,
    PointerRepository,
    ProbeConfigRepository,
    ProbeTemplateRepository,
    RuleRepository,
    SettingRepository,
    UpstreamKeyRepository,
    UpstreamRepository,
)

log = logging.getLogger("router")


class AppConfig:
    """全局配置对象：内存缓存 + 数据库读写，线程安全"""

    def __init__(self):
        self._lock = threading.RLock()
        self._upstreams: list[dict] = []
        self._upstream_keys: dict[str, list[str]] = {}
        self._rules: list[dict] = []
        self._api_keys: list[dict] = []
        self._pointers: list[dict] = []
        self._aggregated_names: list[str] = []
        self._model_groups: dict[str, dict] = {}
        self._probe_configs: dict[str, dict] = {}
        # CH-023：统一聚合实体（static / rule）+ 探测模板
        self._aggregations: dict[str, dict] = {}
        self._probe_templates: list[dict] = []
        self._settings: dict = {}
        self._repos = {
            "upstream": UpstreamRepository(),
            "upstream_key": UpstreamKeyRepository(),
            "rule": RuleRepository(),
            "api_key": ApiKeyRepository(),
            "pointer": PointerRepository(),
            "aggregated": AggregatedNameRepository(),
            "model_group": ModelGroupRepository(),
            "probe_config": ProbeConfigRepository(),
            "aggregation": AggregationRepository(),
            "probe_template": ProbeTemplateRepository(),
            "setting": SettingRepository(),
        }
        self.key_pool = KeyPool()
        self.load()

    # ============================================================
    # 加载 / 重载
    # ============================================================

    def load(self) -> None:
        """从数据库全量加载配置到内存（表不存在时容忍，返回空配置）"""
        import sqlite3
        with self._lock:
            try:
                self._upstreams = self._repos["upstream"].list_all()
                self._rules = self._repos["rule"].list_all()
                self._api_keys = self._repos["api_key"].list_all()
                self._pointers = self._repos["pointer"].list_all()
                self._aggregated_names = self._repos["aggregated"].list_names()
                self._model_groups = self._repos["model_group"].list_all()
                self._probe_configs = self._repos["probe_config"].list_all()
                self._aggregations = self._repos["aggregation"].list_all()
                self._probe_templates = self._repos["probe_template"].list_all()
                self._settings = self._repos["setting"].get_all()
                self._sync_legacy_views()
            except sqlite3.OperationalError:
                log.warning("数据库表不存在，配置为空（请先执行 seed.py 初始化）")
                self._upstreams, self._rules = [], []
                self._api_keys, self._pointers = [], []
                self._aggregated_names, self._settings = [], {}
                self._model_groups, self._probe_configs = {}, {}
                self._aggregations, self._probe_templates = {}, []
            self._load_upstream_keys()
            log.info(f"配置已加载: {len(self._upstreams)} 上游源, {len(self._rules)} 规则, "
                     f"{len(self._api_keys)} 密钥, {len(self._pointers)} 别名, "
                     f"{len(self._aggregations)} 聚合")

    def _sync_legacy_views(self) -> None:
        """把统一聚合实体投射回旧视图（CH-023）

        - `_aggregated_names` ← kind=rule 且启用的名字
        - `_model_groups`     ← kind=static 的行（结构 {upstreams, enabled}）

        这样既有的路由/聚合读取路径（collect_model_upstreams / resolve_group_candidates /
        collect_group_members / is_model_group）无需改动即可继续工作。
        统一表为空时（未迁移的老库）保留旧表加载结果。
        """
        if not self._aggregations:
            return
        self._aggregated_names = [
            name for name, a in self._aggregations.items()
            if a.get("kind") == "rule" and a.get("enabled", True)
        ]
        self._model_groups = {
            name: {"upstreams": a.get("members") or [], "enabled": a.get("enabled", True)}
            for name, a in self._aggregations.items()
            if a.get("kind") == "static"
        }

    def _load_upstream_keys(self) -> None:
        """加载各上游的启用 Key 列表（缺失时回退到 up_upstream.api_key 单 Key）"""
        keys_map: dict[str, list[str]] = {}
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            keys = [k["api_key"] for k in self._repos["upstream_key"].list_by_upstream(uid) if k.get("enabled", 1)]
            if not keys:
                single = (u.get("api_key") or "").strip()
                if single:
                    keys = [single]
            keys_map[uid] = keys
        self._upstream_keys = keys_map

    def reload(self) -> None:
        """热重载：重新从数据库加载"""
        self.load()
        # Key 池可能变化，重置全部运行时 Key 状态
        for uid in self._upstream_keys:
            self.key_pool.reset(uid)
        log.info("配置热重载完成")

    # ============================================================
    # 便捷属性（与 v4 AppConfig 兼容）
    # ============================================================

    @property
    def upstreams(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._upstreams)

    @property
    def rules(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._rules)

    @property
    def api_keys(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._api_keys)

    @property
    def model_pointers(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._pointers)

    @property
    def aggregated_names(self) -> set[str]:
        with self._lock:
            return set(self._aggregated_names)

    @property
    def listen_port(self) -> int:
        return self._settings.get("listen_port", 10002)

    @property
    def default_upstream(self) -> str:
        return self._settings.get("default_upstream", "")

    @property
    def admin_config(self) -> dict:
        return self._settings.get("admin", {})

    @property
    def probe_config(self) -> dict:
        return self._settings.get("latency_probe", {})

    @property
    def failover_config(self) -> dict:
        return self._settings.get("failover", {})

    @property
    def retry_config(self) -> dict:
        return self._settings.get("retry", {})

    @property
    def smart_retry_config(self) -> dict:
        """智能重试全局参数（与缺省值合并，允许只配部分字段）"""
        default = {"extra_attempts": 2, "backoff_ms": [500, 1500], "jitter": 0.2}
        cfg = self._settings.get("smart_retry") or {}
        return {**default, **cfg}

    @property
    def log_level(self) -> str:
        return self._settings.get("log_level", "INFO")

    @property
    def log_routing(self) -> bool:
        return self._settings.get("log_routing", True)

    DEFAULT_GROUPS = [
        {"name": "free", "description": "免费分组（默认）"},
        {"name": "premium", "description": "付费分组"},
    ]

    def get_groups(self) -> list[dict]:
        """获取可配置分组列表（[{name, description}]）"""
        return copy.deepcopy(self._settings.get("groups", self.DEFAULT_GROUPS))

    def set_groups(self, groups: list[dict]) -> None:
        """整体保存分组列表并热重载"""
        cleaned = []
        for g in groups or []:
            name = str(g.get("name", "")).strip()
            if not name:
                continue
            cleaned.append({"name": name, "description": str(g.get("description", "")).strip()})
        self._repos["setting"].set("groups", cleaned)
        self.reload()

    # ============================================================
    # 上游源查询
    # ============================================================

    def get_upstream(self, upstream_id: str) -> dict | None:
        for u in self._upstreams:
            if u.get("upstream_id") == upstream_id:
                return dict(u)
        return None

    def get_upstream_group(self, upstream_id: str) -> str:
        upstream = self.get_upstream(upstream_id)
        return upstream.get("group_name", "free") if upstream else "free"

    def get_upstream_groups(self, upstream_id: str) -> set[str]:
        """上游源归属分组集合（CH-016 多分组；repo 层已回填 groups，空则回退 [group_name]）"""
        upstream = self.get_upstream(upstream_id)
        if not upstream:
            return {"free"}
        groups = upstream.get("groups")
        if isinstance(groups, list) and groups:
            return {str(g) for g in groups}
        return {upstream.get("group_name", "free")}

    def get_model_protocol(self, upstream_id: str, model: str) -> str:
        """模型级协议覆盖：命中 models 条目且带 protocol 则返回，否则回退源级 format"""
        upstream = self.get_upstream(upstream_id)
        if not upstream:
            return "openai"
        for m in upstream.get("models") or []:
            if isinstance(m, dict) and m.get("name") == model and m.get("protocol"):
                return m["protocol"]
        return upstream.get("format", "openai")

    def is_model_enabled(self, upstream_id: str, model: str) -> bool:
        """上游源内单个模型是否启用（CH-019：models 条目缺省 enabled=1）"""
        upstream = self.get_upstream(upstream_id)
        if not upstream:
            return False
        for m in upstream.get("models") or []:
            if isinstance(m, dict) and m.get("name") == model:
                return bool(m.get("enabled", True))
        return True

    def auto_same_name_enabled(self) -> bool:
        """同名模型自动聚合开关（CH-019，sys_setting.auto_same_name_aggregate 默认开）"""
        return bool(self._settings.get("auto_same_name_aggregate", True))

    def get_upstream_keys(self, upstream_id: str) -> list[str]:
        """获取上游源的启用 Key 列表（Key 池）"""
        return list(self._upstream_keys.get(upstream_id, []))

    def get_key_count(self, upstream_id: str) -> int:
        """获取上游源配置的 Key 数量（含禁用的，用于列表展示）"""
        try:
            return len(self._repos["upstream_key"].list_by_upstream(upstream_id))
        except Exception:
            return 0

    def get_upstream_all_keys(self, upstream_id: str) -> list[str]:
        """获取上游源全部 Key（含禁用的，用于管理端编辑回显）"""
        try:
            return [k["api_key"] for k in self._repos["upstream_key"].list_by_upstream(upstream_id)]
        except Exception:
            return []

    def is_upstream_probe_enabled(self, upstream_id: str) -> bool:
        upstream = self.get_upstream(upstream_id)
        if upstream:
            return bool(upstream.get("probe_enabled", True))
        return True

    def is_smart_retry_enabled(self, upstream_id: str) -> bool:
        """上游源是否开启智能重试（同渠道退避重试，CH-012）"""
        upstream = self.get_upstream(upstream_id)
        return bool(upstream.get("smart_retry", False)) if upstream else False

    def is_upstream_enabled(self, upstream_id: str) -> bool:
        """上游源是否启用（禁用后不参与路由/探测/别名/透传，未配置默认启用）"""
        upstream = self.get_upstream(upstream_id)
        if upstream:
            return bool(upstream.get("enabled", True))
        return True

    def get_upstream_for_model(self, model_name: str, candidates: list[dict] | None = None) -> dict:
        if candidates:
            for c in candidates:
                if c.get("model") == model_name:
                    uid = c.get("upstream", self.default_upstream)
                    u = self.get_upstream(uid)
                    if u:
                        return u
        uid = self.default_upstream
        u = self.get_upstream(uid)
        if u:
            return u
        if self._upstreams:
            return dict(self._upstreams[0])
        return {}

    def find_model_upstream(self, model_name: str) -> str:
        """查找模型对应的 upstream_id：路由规则候选 → 上游已配置模型（CH-015，跳过禁用模型 CH-019）→ 默认源"""
        uid = self.collect_model_upstreams(model_name, limit=1)
        if uid:
            return uid[0]
        return self.default_upstream

    def collect_model_upstreams(self, model_name: str, limit: int | None = None) -> list[str]:
        """返回模型可用的全部 upstream_id（按 upstream 展示顺序）
        过滤：上游禁用 / 模型级禁用；规则候选优先于已配置模型列表
        CH-019 二期：若存在人工聚合配置，以配置的勾选与顺序为准（可能含异名成员）"""
        group = self._model_groups.get(model_name)
        if group is not None:
            if not group.get("enabled", True):
                # 关掉聚合 → 退化为单源直连（取配置里的第一个可用源）
                for item in group.get("upstreams", []):
                    uid = item.get("upstream", "")
                    actual = item.get("model") or model_name
                    if self.is_upstream_enabled(uid) and self.is_model_enabled(uid, actual):
                        return [uid]
                return []
            result: list[str] = []
            for item in group.get("upstreams", []):
                uid = item.get("upstream", "")
                actual = item.get("model") or model_name
                if not uid or uid in result:
                    continue
                if self.is_upstream_enabled(uid) and self.is_model_enabled(uid, actual):
                    result.append(uid)
                    if limit and len(result) >= limit:
                        return result
            return result

        matched: list[str] = []
        for rule in self._rules:
            for c in rule.get("candidates", []):
                if c.get("model") == model_name:
                    uid = c.get("upstream", self.default_upstream)
                    if self.is_upstream_enabled(uid) and self.is_model_enabled(uid, model_name):
                        matched.append(uid)
                        if limit and len(matched) >= limit:
                            return matched
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            if uid in matched:
                continue
            if not self.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                if isinstance(m, dict) and m.get("name") == model_name:
                    if self.is_model_enabled(uid, model_name):
                        matched.append(uid)
                        if limit and len(matched) >= limit:
                            return matched
                    break
        return matched

    def resolve_group_candidates(self, group_name: str) -> list[dict]:
        """聚合名 → 候选列表 [{model(真实名), upstream, weight}]
        优先人工配置（支持异名成员）；否则回退同名自动发现"""
        group = self._model_groups.get(group_name)
        if group is None:
            return [
                {"model": group_name, "upstream": uid, "weight": 1}
                for uid in self.collect_model_upstreams(group_name)
            ]
        if not group.get("enabled", True):
            for item in group.get("upstreams", []):
                uid = item.get("upstream", "")
                actual = item.get("model") or group_name
                if self.is_upstream_enabled(uid) and self.is_model_enabled(uid, actual):
                    return [{"model": actual, "upstream": uid, "weight": item.get("weight", 1)}]
            return []
        result: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in group.get("upstreams", []):
            uid = item.get("upstream", "")
            actual = item.get("model") or group_name
            if not uid or (uid, actual) in seen:
                continue
            if not self.is_upstream_enabled(uid) or not self.is_model_enabled(uid, actual):
                continue
            seen.add((uid, actual))
            result.append({"model": actual, "upstream": uid, "weight": item.get("weight", 1)})
        return result

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
        ok = self._repos["aggregation"].delete(name)
        if ok:
            self._refresh_unified()
        return ok

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

    # ============================================================
    # API Key 校验
    # ============================================================

    def validate_api_key(self, raw_key: str) -> dict | None:
        """校验客户端密钥，返回条目或 None"""
        for ak in self._api_keys:
            if ak.get("key_value") == raw_key and ak.get("enabled", True):
                return {
                    "name": ak.get("name", ""),
                    "key": ak.get("key_value", ""),
                    "groups": self._parse_groups(ak.get("groups")),
                    "enabled": ak.get("enabled", True),
                }
        return None

    @staticmethod
    def _parse_groups(groups_raw: str | list | None) -> list[str]:
        if isinstance(groups_raw, list):
            return groups_raw
        import json as _json
        try:
            parsed = _json.loads(groups_raw) if groups_raw else ["free"]
            return parsed if isinstance(parsed, list) else ["free"]
        except Exception:
            return ["free"]

    # ============================================================
    # 模型集合
    # ============================================================

    def get_all_models(self) -> set[str]:
        models = set()
        for rule in self._rules:
            for c in rule.get("candidates", []):
                models.add(c["model"])
        for p in self._pointers:
            t = p.get("target_model", "")
            if t:
                models.add(t)
        return models

    def get_all_candidates_with_limits(self) -> dict[str, dict]:
        result = {}
        for rule in self._rules:
            for c in rule.get("candidates", []):
                m = c["model"]
                if m not in result:
                    result[m] = {
                        "max_context": c.get("max_context"),
                        "max_output": c.get("max_output"),
                    }
        return result

    def get_model_pointer(self, name: str) -> dict | None:
        for p in self._pointers:
            if p.get("name") == name:
                return dict(p)
        return None

    # ============================================================
    # 写操作（Service 层调用，写库 + 更新内存）
    # ============================================================

    def add_upstream(self, data: dict) -> bool:
        ok = self._repos["upstream"].create(data)
        if ok:
            with self._lock:
                self._upstreams = self._repos["upstream"].list_all()
                # 写入 Key 池（api_keys 优先，其次单 api_key）
                keys = data.get("api_keys") or ([data["api_key"]] if data.get("api_key") else [])
                self._repos["upstream_key"].replace(data["id"], keys)
                self._load_upstream_keys()
        return ok

    def update_upstream(self, upstream_id: str, data: dict) -> bool:
        # Key 池整体替换：从 data 中取出 api_keys / api_key 后单独处理
        key_data = dict(data)
        pool_keys = key_data.pop("api_keys", None)
        if pool_keys is not None:
            ok = self._repos["upstream"].update(upstream_id, key_data)
            if ok:
                with self._lock:
                    self._repos["upstream_key"].replace(upstream_id, pool_keys)
                    self._upstreams = self._repos["upstream"].list_all()
                    self._load_upstream_keys()
                    self.key_pool.reset(upstream_id)
            return ok
        if key_data.get("api_key") is not None:
            ok = self._repos["upstream"].update(upstream_id, key_data)
            if ok:
                with self._lock:
                    self._repos["upstream_key"].replace(upstream_id, [key_data["api_key"]])
                    self._upstreams = self._repos["upstream"].list_all()
                    self._load_upstream_keys()
                    self.key_pool.reset(upstream_id)
            return ok
        ok = self._repos["upstream"].update(upstream_id, key_data)
        if ok:
            with self._lock:
                self._upstreams = self._repos["upstream"].list_all()
        return ok

    def delete_upstream(self, upstream_id: str) -> bool:
        ok = self._repos["upstream"].delete(upstream_id)
        if ok:
            with self._lock:
                self._repos["upstream_key"].delete_by_upstream(upstream_id)
                self._upstreams = self._repos["upstream"].list_all()
                self._upstream_keys.pop(upstream_id, None)
                self.key_pool.reset(upstream_id)
        return ok

    def set_rules(self, rules: list[dict]) -> list[str]:
        """整体替换路由规则，并清理 rule 聚合中已失效的绑定（CH-024）

        返回因规则删除/改名而被清理绑定的聚合名。
        """
        self._repos["rule"].replace_all(rules)
        with self._lock:
            self._rules = self._repos["rule"].list_all()
        return self.prune_rule_bindings({r.get("name", "") for r in rules})

    def add_api_key(self, name: str, key_value: str, groups: list | None = None,
                    enabled: bool = True) -> bool:
        groups_raw = groups if groups is not None else ["free"]
        import json as _json
        ok = self._repos["api_key"].create(name, key_value, _json.dumps(groups_raw, ensure_ascii=False), enabled)
        if ok:
            with self._lock:
                self._api_keys = self._repos["api_key"].list_all()
        return ok

    def update_api_key(self, key_value: str, name: str | None = None, groups: list | None = None,
                       enabled: bool | None = None) -> bool:
        import json as _json
        groups_raw = _json.dumps(groups, ensure_ascii=False) if groups is not None else None
        ok = self._repos["api_key"].update(key_value, name=name, groups=groups_raw, enabled=enabled)
        if ok:
            with self._lock:
                self._api_keys = self._repos["api_key"].list_all()
        return ok

    def delete_api_key(self, key_value: str) -> bool:
        ok = self._repos["api_key"].delete(key_value)
        if ok:
            with self._lock:
                self._api_keys = self._repos["api_key"].list_all()
        return ok

    def add_model_pointer(self, name: str, target_model: str, upstream_id: str) -> bool:
        ok = self._repos["pointer"].create(name, target_model, upstream_id)
        if ok:
            with self._lock:
                self._pointers = self._repos["pointer"].list_all()
        return ok

    def update_model_pointer(self, name: str, target_model: str | None = None,
                             upstream_id: str | None = None) -> bool:
        ok = self._repos["pointer"].update(name, target_model, upstream_id)
        if ok:
            with self._lock:
                self._pointers = self._repos["pointer"].list_all()
        return ok

    def delete_model_pointer(self, name: str) -> bool:
        ok = self._repos["pointer"].delete(name)
        if ok:
            with self._lock:
                self._pointers = self._repos["pointer"].list_all()
        return ok

    def set_aggregated_names(self, names: list[str]) -> None:
        """整体替换 rule 类型聚合名（CH-023：写统一表，保留已有探测配置）"""
        cleaned: list[str] = []
        for n in names or []:
            name = str(n).strip()
            if name and name not in cleaned:
                cleaned.append(name)

        existing_rule = {
            name for name, a in self._aggregations.items() if a.get("kind") == "rule"
        }
        for name in existing_rule - set(cleaned):
            self._repos["aggregation"].delete(name)
        for name in cleaned:
            prev = self._aggregations.get(name) or {}
            self._repos["aggregation"].upsert(name, {
                "kind": "rule",
                "members": [],
                "rule_bindings": prev.get("rule_bindings"),
                "enabled": True if prev.get("kind") == "rule" else prev.get("enabled", True),
                "probe_enabled": prev.get("probe_enabled", False),
                "template_id": prev.get("template_id"),
                "sort_mode": prev.get("sort_mode", "stable"),
                "interval_seconds": prev.get("interval_seconds"),
                "slow_threshold_seconds": prev.get("slow_threshold_seconds"),
                "schedule": prev.get("schedule") or {},
                "remark": prev.get("remark") or "",
            })
        self._repos["aggregated"].replace_all(cleaned)
        self._refresh_unified()

    def set_setting(self, key: str, value) -> None:
        self._repos["setting"].set(key, value)
        with self._lock:
            self._settings = self._repos["setting"].get_all()

    def set_admin_config(self, admin: dict) -> None:
        self.set_setting("admin", admin)

    def set_probe_config(self, probe: dict) -> None:
        self.set_setting("latency_probe", probe)

    def set_retry_config(self, retry: dict) -> None:
        self.set_setting("retry", retry)

    def set_smart_retry_config(self, data: dict) -> None:
        self.set_setting("smart_retry", data)

    def set_failover_config(self, failover: dict) -> None:
        self.set_setting("failover", failover)
        self.key_pool.update_config(
            failover.get("max_fails", 3),
            failover.get("cooldown_seconds", 120),
        )


# 全局单例
config = AppConfig()

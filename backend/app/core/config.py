"""
配置仓库 - 内存缓存 + SQLite 持久化 + 热重载（CH-026 按职责拆分）

本文件只保留：类骨架 + 初始化 + 配置加载/重载 + 只读属性 + 分组管理。
其余职责拆到同目录的 mixin：
  - config_upstream.py    上游源查询 / Key 池 / 模型解析
  - config_aggregation.py 聚合实体 / 规则绑定 / 探测配置与计划
  - config_settings.py    密钥校验 / 各类写操作
AppConfig 通过多重继承组合，对外方法签名与拆分前完全一致。
"""

import copy
import logging
import threading

from app.core.key_pool import KeyPool
from app.core.config_aggregation import AggregationConfigMixin
from app.core.config_probe_plan import ProbePlanConfigMixin
from app.core.config_settings import SettingsConfigMixin
from app.core.config_upstream import UpstreamConfigMixin
from app.core.probe_schedule import is_active as schedule_is_active
from app.repositories import (
    AggregatedNameRepository,
    AggregationRepository,
    ApiKeyRepository,
    FilterRuleRepository,
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


class AppConfig(
    UpstreamConfigMixin,
    AggregationConfigMixin,
    ProbePlanConfigMixin,
    SettingsConfigMixin,
):
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
        # CH-041：请求过滤规则（转发前拦截）
        self._filter_rules: list[dict] = []
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
            "filter_rule": FilterRuleRepository(),
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
                self._filter_rules = self._repos["filter_rule"].list_all()
                self._sync_legacy_views()
            except sqlite3.OperationalError:
                log.warning("数据库表不存在，配置为空（请先执行 seed.py 初始化）")
                self._upstreams, self._rules = [], []
                self._api_keys, self._pointers = [], []
                self._aggregated_names, self._settings = [], {}
                self._model_groups, self._probe_configs = {}, {}
                self._aggregations, self._probe_templates = {}, []
                self._filter_rules = []
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

    # ---------- CH-041：请求过滤 ----------

    @property
    def filter_rules(self) -> list[dict]:
        """全部过滤规则（含未启用的；引擎内部自行按 enabled 判断）"""
        with self._lock:
            return copy.deepcopy(self._filter_rules)

    @property
    def filter_engine_enabled(self) -> bool:
        """全局开关，默认 False —— 保证未显式开启时行为与升级前完全一致"""
        return bool(self._settings.get("filter_engine_enabled", False))

    def set_filter_engine_enabled(self, enabled: bool) -> None:
        self._repos["setting"].set("filter_engine_enabled", bool(enabled))
        with self._lock:
            self._settings["filter_engine_enabled"] = bool(enabled)

    def list_filter_rules(self) -> list[dict]:
        return self.filter_rules

    def save_filter_rule(self, data: dict, rule_id: int | None = None) -> int:
        """新建或更新一条规则，并即时刷新内存缓存"""
        if rule_id is None:
            new_id = self._repos["filter_rule"].create(data)
        else:
            self._repos["filter_rule"].update(rule_id, data)
            new_id = rule_id
        with self._lock:
            self._filter_rules = self._repos["filter_rule"].list_all()
        return new_id

    def delete_filter_rule(self, rule_id: int) -> bool:
        ok = self._repos["filter_rule"].delete(rule_id)
        if ok:
            with self._lock:
                self._filter_rules = self._repos["filter_rule"].list_all()
        return ok

    def apply_filter_rules(self, candidates: list[dict], body: dict) -> tuple[list[dict], list[dict]]:
        """按当前规则过滤候选（供路由层调用；引擎关闭时直接原样返回）"""
        from app.core.filter_engine import filter_candidates

        return filter_candidates(
            self.filter_rules, candidates, body, self.filter_engine_enabled,
        )

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

    @property
    def aggregation_order(self) -> list[str]:
        """聚合列表的人工排序（CH-028）；空列表表示沿用 kind+name 默认顺序"""
        raw = self._settings.get("aggregation_order") or []
        return [str(n) for n in raw if isinstance(n, str) and n]

    def set_aggregation_order(self, names: list[str]) -> None:
        """整体保存聚合列表顺序（存 sys_setting，不动 agg_unified 表结构）"""
        cleaned = [str(n) for n in (names or []) if str(n).strip()]
        self.set_setting("aggregation_order", cleaned)


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

# 全局单例
config = AppConfig()

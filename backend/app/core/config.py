"""
配置仓库 - 内存缓存 + SQLite 持久化 + 热重载
替代 v4 的 core/config.py（YAML 存储改为数据库存储）。
提供与 v4 兼容的属性和方法接口，供路由引擎/探测/健康模块使用。
"""

import copy
import logging
import threading

from app.core.key_pool import KeyPool
from app.repositories import (
    AggregatedNameRepository,
    ApiKeyRepository,
    PointerRepository,
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
        self._settings: dict = {}
        self._repos = {
            "upstream": UpstreamRepository(),
            "upstream_key": UpstreamKeyRepository(),
            "rule": RuleRepository(),
            "api_key": ApiKeyRepository(),
            "pointer": PointerRepository(),
            "aggregated": AggregatedNameRepository(),
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
                self._settings = self._repos["setting"].get_all()
            except sqlite3.OperationalError:
                log.warning("数据库表不存在，配置为空（请先执行 seed.py 初始化）")
                self._upstreams, self._rules = [], []
                self._api_keys, self._pointers = [], []
                self._aggregated_names, self._settings = [], {}
            self._load_upstream_keys()
            log.info(f"配置已加载: {len(self._upstreams)} 上游源, {len(self._rules)} 规则, "
                     f"{len(self._api_keys)} 密钥, {len(self._pointers)} 别名")

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

    def get_model_protocol(self, upstream_id: str, model: str) -> str:
        """模型级协议覆盖：命中 models 条目且带 protocol 则返回，否则回退源级 format"""
        upstream = self.get_upstream(upstream_id)
        if not upstream:
            return "openai"
        for m in upstream.get("models") or []:
            if isinstance(m, dict) and m.get("name") == model and m.get("protocol"):
                return m["protocol"]
        return upstream.get("format", "openai")

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
        """查找模型对应的 upstream_id：路由规则候选 → 上游已配置模型（CH-015）→ 默认源"""
        for rule in self._rules:
            for c in rule.get("candidates", []):
                if c.get("model") == model_name:
                    return c.get("upstream", self.default_upstream)
        for u in self._upstreams:
            uid = u.get("upstream_id", "")
            if not self.is_upstream_enabled(uid):
                continue
            for m in u.get("models") or []:
                if isinstance(m, dict) and m.get("name") == model_name:
                    return uid
        return self.default_upstream

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

    def set_rules(self, rules: list[dict]) -> None:
        self._repos["rule"].replace_all(rules)
        with self._lock:
            self._rules = self._repos["rule"].list_all()

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
        self._repos["aggregated"].replace_all(names)
        with self._lock:
            self._aggregated_names = self._repos["aggregated"].list_names()

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

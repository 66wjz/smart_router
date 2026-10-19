"""
系统设置写入与密钥校验（CH-026 从 config.py 按职责拆出）

覆盖：API Key 校验、上游/规则/别名/密钥的写操作、系统参数写入。
AppConfig 通过多重继承组合，对外方法签名不变。
"""

import json
import logging

log = logging.getLogger("router")


class SettingsConfigMixin:
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
                "groups": prev.get("groups") or [],
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

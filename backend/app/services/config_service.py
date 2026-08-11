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

    def set_rules(self, rules: list) -> None:
        self.config.set_rules(rules)

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

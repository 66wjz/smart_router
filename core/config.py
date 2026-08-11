"""
配置管理模块 - 加载/保存/热重载 config.yaml
全局单例 AppConfig，其他模块从中读取配置。
"""

import copy
import logging
import os
import threading
from typing import Any

import yaml

log = logging.getLogger("router")

# 默认配置文件路径（与 router.py 同目录）
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")


class AppConfig:
    """全局配置对象，线程安全，支持热重载"""

    def __init__(self, config_path: str = CONFIG_PATH):
        self._path = config_path
        self._lock = threading.RLock()
        self._data: dict = {}
        self.load()

    # ---------- 读写 ----------

    def load(self) -> None:
        """从文件加载配置"""
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
            log.info(f"配置已加载: {self._path}")

    def save(self) -> None:
        """保存当前配置到文件"""
        with self._lock:
            with open(self._path, "w", encoding="utf-8") as f:
                yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            log.info(f"配置已保存: {self._path}")

    def reload(self) -> None:
        """热重载：重新读取配置文件"""
        self.load()
        log.info("配置热重载完成")

    def get_raw(self) -> dict:
        """返回配置的深拷贝（安全）"""
        with self._lock:
            return copy.deepcopy(self._data)

    # ---------- 便捷属性 ----------

    @property
    def listen_port(self) -> int:
        return self._data.get("listen_port", 10002)

    @property
    def default_upstream(self) -> str:
        return self._data.get("default_upstream", "")

    @property
    def aggregated_names(self) -> set[str]:
        return set(self._data.get("aggregated_model_names", []))

    @property
    def upstreams(self) -> list[dict]:
        return self._data.get("upstreams", [])

    @property
    def rules(self) -> list[dict]:
        return self._data.get("rules", [])

    @property
    def admin_config(self) -> dict:
        return self._data.get("admin", {})

    @property
    def probe_config(self) -> dict:
        return self._data.get("latency_probe", {})

    @property
    def failover_config(self) -> dict:
        return self._data.get("failover", {})

    @property
    def retry_config(self) -> dict:
        return self._data.get("retry", {})

    @property
    def log_level(self) -> str:
        return self._data.get("log_level", "INFO")

    @property
    def log_routing(self) -> bool:
        return self._data.get("log_routing", True)

    @property
    def model_pointers(self) -> list[dict]:
        """模型别名列表，每项: {name, target_model, upstream}"""
        return self._data.get("model_pointers", [])

    # ---------- 路由层 API Key ----------

    @property
    def api_keys(self) -> list[dict]:
        """路由层 API Key 列表，每项: {name, key, groups, enabled}"""
        return self._data.get("api_keys", [])

    def validate_api_key(self, raw_key: str) -> dict | None:
        """
        校验客户端传入的 key 是否在白名单中且已启用。
        返回 key 条目 dict（含 name/key/groups/enabled），无效则返回 None。
        raw_key 不含 'Bearer ' 前缀。
        """
        with self._lock:
            for ak in self._data.get("api_keys", []):
                if ak.get("key") == raw_key and ak.get("enabled", True):
                    return copy.deepcopy(ak)
            return None

    def add_api_key(self, entry: dict) -> bool:
        """添加 API Key，key 重复返回 False"""
        with self._lock:
            new_key = entry.get("key", "")
            if any(ak.get("key") == new_key for ak in self._data.get("api_keys", [])):
                return False
            self._data.setdefault("api_keys", []).append(entry)
            self.save()
            return True

    def update_api_key(self, key_value: str, updates: dict) -> bool:
        """更新 API Key，不存在返回 False。不允许改 key 字段本身"""
        with self._lock:
            for ak in self._data.get("api_keys", []):
                if ak.get("key") == key_value:
                    ak.update(updates)
                    ak["key"] = key_value  # 不允许改 key 值
                    self.save()
                    return True
            return False

    def delete_api_key(self, key_value: str) -> bool:
        """删除 API Key"""
        with self._lock:
            keys = self._data.get("api_keys", [])
            before = len(keys)
            self._data["api_keys"] = [ak for ak in keys if ak.get("key") != key_value]
            if len(self._data["api_keys"]) < before:
                self.save()
                return True
            return False

    def get_model_pointer(self, name: str) -> dict | None:
        """根据别名名获取指针配置"""
        for p in self.model_pointers:
            if p.get("name") == name:
                return copy.deepcopy(p)
        return None

    def model_pointer_names(self) -> set[str]:
        """所有别名名的集合"""
        return {p.get("name", "") for p in self.model_pointers}

    def set_model_pointers(self, pointers: list[dict]) -> None:
        """替换模型别名列表"""
        with self._lock:
            self._data["model_pointers"] = pointers
            self.save()

    def add_model_pointer(self, pointer: dict) -> bool:
        """添加模型别名，name 重复返回 False"""
        with self._lock:
            name = pointer.get("name", "")
            if any(p.get("name") == name for p in self._data.get("model_pointers", [])):
                return False
            self._data.setdefault("model_pointers", []).append(pointer)
            self.save()
            return True

    def update_model_pointer(self, name: str, updates: dict) -> bool:
        """更新模型别名，不存在返回 False"""
        with self._lock:
            for p in self._data.get("model_pointers", []):
                if p.get("name") == name:
                    p.update(updates)
                    p["name"] = name  # 不允许改 name
                    self.save()
                    return True
            return False

    def delete_model_pointer(self, name: str) -> bool:
        """删除模型别名"""
        with self._lock:
            pointers = self._data.get("model_pointers", [])
            before = len(pointers)
            self._data["model_pointers"] = [p for p in pointers if p.get("name") != name]
            if len(self._data["model_pointers"]) < before:
                self.save()
                return True
            return False

    # ---------- 上游源查询 ----------

    def get_upstream(self, upstream_id: str) -> dict | None:
        """根据 id 获取上游源配置"""
        for u in self.upstreams:
            if u.get("id") == upstream_id:
                return copy.deepcopy(u)
        return None

    def get_upstream_group(self, upstream_id: str) -> str:
        """
        获取上游源所属分组。
        未配置 group 字段的默认归为 "free"。
        """
        upstream = self.get_upstream(upstream_id)
        if upstream:
            return upstream.get("group", "free")
        return "free"

    def is_upstream_probe_enabled(self, upstream_id: str) -> bool:
        """
        该上游源是否参与延迟探测。
        未配置 probe_enabled 字段默认为 True。
        """
        upstream = self.get_upstream(upstream_id)
        if upstream:
            return upstream.get("probe_enabled", True)
        return True

    def get_vision_pipeline(self, upstream_id: str) -> dict | None:
        """
        获取上游源的视觉预处理管道配置。
        返回 vision_pipeline dict（含 enabled/intent_model/vision_model/vision_upstream），
        未配置则返回 None。
        """
        upstream = self.get_upstream(upstream_id)
        if upstream:
            return upstream.get("vision_pipeline")
        return None

    def get_upstream_for_model(self, model_name: str, candidates: list[dict] | None = None) -> dict:
        """
        获取模型对应的上游源配置。
        优先从 candidates 列表中查找（路由场景），其次使用 default_upstream。
        """
        # 从候选列表查找
        if candidates:
            for c in candidates:
                if c.get("model") == model_name:
                    uid = c.get("upstream", self.default_upstream)
                    u = self.get_upstream(uid)
                    if u:
                        return u

        # 直接透传场景：用 default_upstream
        uid = self.default_upstream
        u = self.get_upstream(uid)
        if u:
            return u

        # 兜底：返回第一个上游源
        if self.upstreams:
            return copy.deepcopy(self.upstreams[0])
        return {}

    def find_model_upstream(self, model_name: str) -> str:
        """在所有路由规则中查找模型对应的 upstream_id，找不到则返回 default_upstream"""
        for rule in self.rules:
            for c in rule.get("candidates", []):
                if c.get("model") == model_name:
                    return c.get("upstream", self.default_upstream)
        return self.default_upstream

    # ---------- 模型集合 ----------

    def get_all_models(self) -> set[str]:
        """收集所有候选模型名（去重）"""
        models = set()
        for rule in self.rules:
            for c in rule.get("candidates", []):
                models.add(c["model"])
        # 也包含模型别名指向的目标模型
        for p in self.model_pointers:
            t = p.get("target_model", "")
            if t:
                models.add(t)
        return models

    def get_all_candidates_with_limits(self) -> dict[str, dict]:
        """收集所有候选模型的上下文限制（全规则去重）"""
        result = {}
        for rule in self.rules:
            for c in rule.get("candidates", []):
                m = c["model"]
                if m not in result:
                    result[m] = {
                        "max_context": c.get("max_context"),
                        "max_output": c.get("max_output"),
                    }
        return result

    # ---------- CRUD 操作（供 admin API 使用）----------

    def add_upstream(self, upstream: dict) -> bool:
        """添加上游源，id 重复则返回 False"""
        with self._lock:
            uid = upstream.get("id", "")
            if any(u.get("id") == uid for u in self._data.get("upstreams", [])):
                return False
            self._data.setdefault("upstreams", []).append(upstream)
            self.save()
            return True

    def update_upstream(self, upstream_id: str, updates: dict) -> bool:
        """更新上游源，不存在则返回 False"""
        with self._lock:
            for u in self._data.get("upstreams", []):
                if u.get("id") == upstream_id:
                    u.update(updates)
                    # 不允许改 id
                    u["id"] = upstream_id
                    self.save()
                    return True
            return False

    def delete_upstream(self, upstream_id: str) -> bool:
        """删除上游源，不存在则返回 False"""
        with self._lock:
            upstreams = self._data.get("upstreams", [])
            before = len(upstreams)
            self._data["upstreams"] = [u for u in upstreams if u.get("id") != upstream_id]
            if len(self._data["upstreams"]) < before:
                self.save()
                return True
            return False

    def set_rules(self, rules: list[dict]) -> None:
        """替换路由规则"""
        with self._lock:
            self._data["rules"] = rules
            self.save()

    def set_aggregated_names(self, names: list[str]) -> None:
        """替换聚合模型名"""
        with self._lock:
            self._data["aggregated_model_names"] = names
            self.save()

    def set_admin_config(self, admin: dict) -> None:
        """更新管理后台配置"""
        with self._lock:
            self._data["admin"] = admin
            self.save()

    def set_probe_config(self, probe: dict) -> None:
        """更新延迟探测配置"""
        with self._lock:
            self._data["latency_probe"] = probe
            self.save()

    def set_retry_config(self, retry: dict) -> None:
        """更新重试配置"""
        with self._lock:
            self._data["retry"] = retry
            self.save()

    def set_failover_config(self, failover: dict) -> None:
        """更新故障转移配置"""
        with self._lock:
            self._data["failover"] = failover
            self.save()


# 全局单例
config = AppConfig()

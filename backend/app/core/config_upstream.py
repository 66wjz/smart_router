"""
上游源查询与模型解析（CH-026 从 config.py 按职责拆出）

AppConfig 通过多重继承组合这些 mixin，对外方法签名与拆分前完全一致。
本 mixin 假定宿主已提供：self._lock / self._upstreams / self._upstream_keys /
self._api_keys / self._model_groups / self._aggregations / self._repos / self.key_pool /
self._settings 等属性。
"""

import copy
import logging

log = logging.getLogger("router")


class UpstreamConfigMixin:
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
        """同名模型自动聚合开关（CH-019；CH-036 默认改为关闭）

        关闭时：「同名模型分布在多个源」不再被当成聚合组，但不影响跨源兜底
        （collect_model_upstreams 仍返回多候选）。
        """
        return bool(self._settings.get("auto_same_name_aggregate", False))

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

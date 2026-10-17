"""
仪表盘服务 - 聚合统计数据
CH-019：探测/健康按 (upstream, model) 隔离后，仪表盘统计同步按 key 粒度展开
"""

from typing import TYPE_CHECKING

from app.core.probe import LatencyProbe

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.health import ModelHealth


class DashboardService:
    def __init__(self, config: "AppConfig", probe: "LatencyProbe", health: "ModelHealth"):
        self.config = config
        self.probe = probe
        self.health = health

    def get_dashboard(self) -> dict:
        """聚合仪表盘数据"""
        all_models = self.config.get_all_models()
        # 每个 (upstream, model) 组合都是独立探测单元
        probe_units: list[tuple[str, str]] = []
        for m in all_models:
            for uid in self.config.collect_model_upstreams(m):
                if self.config.is_upstream_probe_enabled(uid):
                    probe_units.append((uid, m))

        model_ok = sum(1 for uid, m in probe_units if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "ok")
        model_down = sum(1 for uid, m in probe_units if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "down")
        model_unknown = len(probe_units) - model_ok - model_down

        # 合并健康状态：转发故障(fails/cooldown) + 探测故障(probe_down)
        health = self.health.get_status()
        health["probe_down"] = {
            f"{m}@{uid}": self.probe.data.get(LatencyProbe._key(uid, m), {}).get("error") or "down"
            for uid, m in probe_units
            if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "down"
        }

        return {
            "upstream_count": len(self.config.upstreams),
            "model_count": len(all_models),
            "probe_unit_count": len(probe_units),
            "model_ok": model_ok,
            "model_down": model_down + model_unknown,
            "rule_count": len(self.config.rules),
            "pointer_count": len(self.config.model_pointers),
            "api_key_count": len(self.config.api_keys),
            "health": health,
        }

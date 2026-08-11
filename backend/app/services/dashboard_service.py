"""
仪表盘服务 - 聚合统计数据
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.probe import LatencyProbe
    from app.core.health import ModelHealth


class DashboardService:
    def __init__(self, config: "AppConfig", probe: "LatencyProbe", health: "ModelHealth"):
        self.config = config
        self.probe = probe
        self.health = health

    def get_dashboard(self) -> dict:
        """聚合仪表盘数据"""
        all_models = self.config.get_all_models()
        model_ok = sum(1 for m in all_models if self.probe.data.get(m, {}).get("status") == "ok")
        model_down = sum(1 for m in all_models if self.probe.data.get(m, {}).get("status") == "down")
        model_unknown = len(all_models) - model_ok - model_down

        # 合并健康状态：转发故障(fails/cooldown) + 探测故障(probe_down)
        health = self.health.get_status()
        health["probe_down"] = {
            m: self.probe.data.get(m, {}).get("error") or "down"
            for m in all_models
            if self.probe.data.get(m, {}).get("status") == "down"
        }

        return {
            "upstream_count": len(self.config.upstreams),
            "model_count": len(all_models),
            "model_ok": model_ok,
            "model_down": model_down + model_unknown,
            "rule_count": len(self.config.rules),
            "pointer_count": len(self.config.model_pointers),
            "api_key_count": len(self.config.api_keys),
            "health": health,
        }

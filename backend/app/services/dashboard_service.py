"""
仪表盘服务 - 聚合统计数据

CH-019：探测/健康按 (upstream, model) 隔离后，统计同步按 key 粒度展开
CH-022：扩展为完整仪表盘（今日/7天用量、日趋势、上游贡献占比、聚合组概览、待关注项、探测摘要）
"""

from typing import TYPE_CHECKING

from app.core.probe import LatencyProbe
from app.core.probe_schedule import describe as describe_schedule

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.health import ModelHealth


class DashboardService:
    def __init__(self, config: "AppConfig", probe: "LatencyProbe", health: "ModelHealth"):
        self.config = config
        self.probe = probe
        self.health = health

    # ------------------------------------------------------------
    # 探测 / 健康
    # ------------------------------------------------------------

    def _probe_units(self) -> list[tuple[str, str]]:
        all_models = self.config.get_all_models()
        units: list[tuple[str, str]] = []
        for m in all_models:
            for uid in self.config.collect_model_upstreams(m):
                if self.config.is_upstream_probe_enabled(uid):
                    units.append((uid, m))
        return units

    def _probe_summary(self) -> dict:
        plan = self.config.collect_probe_plan()
        ok = down = unknown = 0
        scheduled_off = 0
        for key, item in plan.items():
            info = self.probe.data.get(key) or {}
            status = info.get("status", "unknown")
            if status == "ok":
                ok += 1
            elif status == "down":
                down += 1
            else:
                unknown += 1
            if not self.config.probe_plan_active(item):
                scheduled_off += 1
        global_cfg = self.config.probe_config
        return {
            "enabled": bool(global_cfg.get("enabled", True)) or any(
                self.config.group_probe_settings(g)["enabled"] for g in self.config.collect_group_members()
            ),
            "unit_count": len(plan),
            "ok": ok,
            "down": down,
            "unknown": unknown,
            "global_interval": global_cfg.get("interval_seconds", 120),
            "global_schedule": describe_schedule(global_cfg.get("schedule")),
            "scheduled_off": scheduled_off,
        }

    def _attention(self) -> list[dict]:
        """需要关注的异常项：冷却中 / 探测不可用 / 数据陈旧 / 上游无 Key / 上游已禁用"""
        items: list[dict] = []
        now_units = self._probe_units()
        panel = self.probe.get_panel()

        health = self.health.get_status()
        for key, remain in (health.get("cooldown") or {}).items():
            if remain > 0:
                upstream_id, _, model = key.partition(":")
                items.append({
                    "kind": "cooldown",
                    "target": f"{model}@{upstream_id}",
                    "detail": f"冷却剩余 {remain}s",
                })

        down_keys = {i["target"].split("@")[0] + "@" + i["target"].split("@")[-1] for i in items}
        for uid, model in now_units:
            key = LatencyProbe._key(uid, model)
            info = self.probe.data.get(key) or {}
            if info.get("status") == "down":
                target = f"{model}@{uid}"
                if target in down_keys:
                    continue
                items.append({
                    "kind": "probe_down",
                    "target": target,
                    "detail": f"探测不可用：{info.get('error') or 'unknown'}",
                })

        for key, info in panel.items():
            if info.get("stale"):
                uid, _, model = key.partition(":")
                if any(i["kind"] == "probe_down" and i["target"] == f"{model}@{uid}" for i in items):
                    continue
                items.append({
                    "kind": "stale",
                    "target": f"{model}@{uid}",
                    "detail": f"数据陈旧（间隔 {info.get('interval')}s 未更新）",
                })

        for u in self.config.upstreams:
            uid = u.get("upstream_id", "")
            if not u.get("enabled", True):
                items.append({
                    "kind": "disabled_upstream",
                    "target": u.get("name", uid),
                    "detail": "上游源已禁用，不参与路由与探测",
                })
                continue
            if not self.config.get_upstream_keys(uid):
                items.append({
                    "kind": "no_key",
                    "target": u.get("name", uid),
                    "detail": "未配置任何可用 Key",
                })

        order = {"cooldown": 0, "probe_down": 1, "no_key": 2, "stale": 3, "disabled_upstream": 4}
        items.sort(key=lambda i: order.get(i["kind"], 9))
        return items[:20]

    # ------------------------------------------------------------
    # 用量 / 聚合组
    # ------------------------------------------------------------

    def _usage_repo(self):
        from app.repositories.usage_repo import UsageRepository
        return UsageRepository()

    def _usage_block(self) -> dict:
        repo = self._usage_repo()
        today = repo.summary("today")
        week = repo.summary("7d")
        trend = repo.daily_trend(7)
        # 环比：今日（0 点到现在）vs 昨日同期（昨日 0 点到昨天同一时刻），避免"半天 vs 全天"的误导
        delta = None
        try:
            from datetime import datetime, timedelta
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start = today_start - timedelta(days=1)
            y_same = yesterday_start + (now - today_start)
            cur = repo.count_in_period(today_start.timestamp(), now.timestamp())
            prev = repo.count_in_period(yesterday_start.timestamp(), y_same.timestamp())
            if prev > 0:
                delta = round((cur - prev) / prev, 4)
        except Exception:
            delta = None
        return {
            "usage_today": {
                "requests": today.get("total", 0),
                "success_rate": today.get("success_rate"),
                "total_tokens": today.get("total_tokens", 0),
                "active_keys": today.get("active_keys", 0),
                "requests_delta": delta,
            },
            "usage_7d": {
                "requests": week.get("total", 0),
                "total_tokens": week.get("total_tokens", 0),
                "success_rate": week.get("success_rate"),
            },
            "trend": trend,
        }

    def _upstream_usage(self) -> list[dict]:
        rows = self._usage_repo().by_upstream("7d")
        probe_by_upstream: dict[str, dict[str, int]] = {}
        for uid, _model in self._probe_units():
            info = self.probe.data.get(LatencyProbe._key(uid, _model)) or {}
            slot = probe_by_upstream.setdefault(uid, {"ok": 0, "total": 0})
            slot["total"] += 1
            if info.get("status") == "ok":
                slot["ok"] += 1

        live = {u.get("upstream_id"): u for u in self.config.upstreams}
        for row in rows:
            uid = row.get("upstream_id")
            slot = probe_by_upstream.get(uid) or {"ok": 0, "total": 0}
            row["probe_ok"] = slot["ok"]
            row["probe_total"] = slot["total"]
            row["enabled"] = bool((live.get(uid) or {}).get("enabled", True))
            row["smart_retry"] = bool((live.get(uid) or {}).get("smart_retry", False))
        return rows

    def _group_overview(self) -> list[dict]:
        """聚合组概览：成员链路 + 探测配置 + 近 7 天用量"""
        members_map = self.config.collect_group_members()
        if not members_map:
            return []
        configured = self.config.get_model_groups()
        usage = {r["model"]: r for r in self._usage_repo().by_request_model("7d")}
        result = []
        for name, members in sorted(members_map.items()):
            settings = self.config.group_probe_settings(name)
            used = usage.get(name) or {}
            result.append({
                "model": name,
                "member_count": len(members),
                "members": members,
                "configured": name in configured,
                "probe_enabled": bool(settings["enabled"]),
                "probe_interval": settings["interval_seconds"],
                "probe_schedule": describe_schedule(settings["schedule"]),
                "probe_schedule_mode": (settings["schedule"] or {}).get("mode", "always"),
                "sort_mode": settings["sort_mode"],
                "requests_7d": used.get("requests", 0),
                "tokens_7d": used.get("total_tokens", 0),
            })
        # 有流量的优先，其次手动配置的优先
        result.sort(key=lambda g: (-g["tokens_7d"], not g["configured"], g["model"]))
        return result

    # ------------------------------------------------------------
    # 对外
    # ------------------------------------------------------------

    def get_dashboard(self) -> dict:
        all_models = self.config.get_all_models()
        probe_units = self._probe_units()
        model_ok = sum(
            1 for uid, m in probe_units
            if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "ok"
        )
        model_down = sum(
            1 for uid, m in probe_units
            if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "down"
        )
        model_unknown = len(probe_units) - model_ok - model_down

        health = self.health.get_status()
        health["probe_down"] = {
            f"{m}@{uid}": self.probe.data.get(LatencyProbe._key(uid, m), {}).get("error") or "down"
            for uid, m in probe_units
            if self.probe.data.get(LatencyProbe._key(uid, m), {}).get("status") == "down"
        }

        payload = {
            "upstream_count": len(self.config.upstreams),
            "model_count": len(all_models),
            "probe_unit_count": len(probe_units),
            "model_ok": model_ok,
            "model_down": model_down + model_unknown,
            "rule_count": len(self.config.rules),
            "pointer_count": len(self.config.model_pointers),
            "api_key_count": len(self.config.api_keys),
            "health": health,
            "probe_summary": self._probe_summary(),
            "attention": self._attention(),
            "upstream_usage": self._upstream_usage(),
            "groups": self._group_overview(),
        }
        try:
            payload.update(self._usage_block())
        except Exception:
            # 用量表尚未建立时仪表盘仍可用
            payload.update({
                "usage_today": {"requests": 0, "success_rate": None, "total_tokens": 0,
                                "active_keys": 0, "requests_delta": None},
                "usage_7d": {"requests": 0, "total_tokens": 0, "success_rate": None},
                "trend": [],
            })
        return payload

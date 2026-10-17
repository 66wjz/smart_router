"""CH-021 验证脚本（不联网、不写库）

覆盖：
1. 时段判定（schedule）
2. 探测计划去重 + 间隔取最小
3. 排序 stable / latency + 全 down 兜底
4. 探测失败不计 Key 冷却（需 mock HTTP）
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core.probe_schedule import is_active, normalize_schedule

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ============================================================
# 1. 时段
# ============================================================
print("\n[1] 探测时段")

always = {"mode": "always"}
check("always 全天都算", is_active(always, datetime(2026, 10, 17, 3, 0)))

workday_day = {"mode": "window", "days": [1, 2, 3, 4, 5], "windows": [{"start": "00:00", "end": "23:59"}]}
check("工作日-周五 命中", is_active(workday_day, datetime(2026, 10, 16, 12, 0)))   # 周五
check("工作日-周六 不命中", not is_active(workday_day, datetime(2026, 10, 17, 12, 0)))  # 周六

night_off = {"mode": "window", "windows": [{"start": "08:00", "end": "23:00"}]}
check("08:30 命中", is_active(night_off, datetime(2026, 10, 17, 8, 30)))
check("23:30 不命中（夜间不探）", not is_active(night_off, datetime(2026, 10, 17, 23, 30)))
check("07:00 不命中", not is_active(night_off, datetime(2026, 10, 17, 7, 0)))
check("22:59 边界内", is_active(night_off, datetime(2026, 10, 17, 22, 59)))

cross_night = {"mode": "window", "windows": [{"start": "23:00", "end": "07:00"}]}
check("跨夜 02:00 命中", is_active(cross_night, datetime(2026, 10, 17, 2, 0)))
check("跨夜 12:00 不命中", not is_active(cross_night, datetime(2026, 10, 17, 12, 0)))

weekend_off = {"mode": "window", "days": [1, 2, 3, 4, 5]}
check("周末不探测（周六）", not is_active(weekend_off, datetime(2026, 10, 17, 10, 0)))
check("周末不探测（周日）", not is_active(weekend_off, datetime(2026, 10, 18, 10, 0)))

check("非法输入回退 always", normalize_schedule({"mode": "xxx"})["mode"] == "always")
check("非法时间被剔除", normalize_schedule(
    {"mode": "window", "windows": [{"start": "99:00", "end": "07:00"}]})["windows"] == [])


# ============================================================
# 2/3. 探测计划 + 排序（用轻量假配置，不连库）
# ============================================================
print("\n[2] 探测计划去重 / 排序")

from app.core.probe import LatencyProbe
from app.core.health import ModelHealth


class FakeConfig:
    """最小实现：两个聚合组共享 loomy 成员"""

    def __init__(self):
        self.probe_config = {"enabled": True, "interval_seconds": 360,
                             "slow_threshold_seconds": 10, "max_concurrency": 3}
        self._groups = {
            "g1": {"enabled": True, "members": [
                {"upstream": "buddy", "model": "deepseek-flash"},
                {"upstream": "loomy", "model": "DeepSeek-Flash"},
            ]},
            "g2": {"enabled": True, "members": [
                {"upstream": "loomy", "model": "DeepSeek-Flash"},
                {"upstream": "trae", "model": "deepseek-flash"},
            ]},
        }
        self._probe_cfgs = {
            "g1": {"enabled": True, "interval_seconds": 60, "slow_threshold_seconds": 6,
                   "sort_mode": "latency", "schedule": {"mode": "always"}},
            "g2": {"enabled": True, "interval_seconds": 300, "slow_threshold_seconds": None,
                   "sort_mode": "stable", "schedule": {"mode": "always"}},
        }

    def collect_group_members(self):
        return {k: list(v["members"]) for k, v in self._groups.items()}

    def get_probe_configs(self):
        return dict(self._probe_cfgs)

    def group_probe_settings(self, name):
        conf = self._probe_cfgs.get(name) or {}
        return {
            "enabled": bool(conf.get("enabled", False)),
            "interval_seconds": conf.get("interval_seconds") or self.probe_config["interval_seconds"],
            "slow_threshold_seconds": conf.get("slow_threshold_seconds")
            if conf.get("slow_threshold_seconds") is not None
            else self.probe_config["slow_threshold_seconds"],
            "sort_mode": conf.get("sort_mode") or "stable",
            "schedule": conf.get("schedule") or {"mode": "always"},
            "configured": bool(conf),
        }

    def collect_probe_plan(self):
        """复刻 AppConfig 的去重逻辑（成员来源只有聚合组）"""
        plan = {}
        for gname, members in self.collect_group_members().items():
            st = self.group_probe_settings(gname)
            if not st["enabled"]:
                continue
            for m in members:
                key = f'{m["upstream"]}:{m["model"]}'
                entry = plan.get(key)
                if entry is None:
                    plan[key] = {"upstream": m["upstream"], "model": m["model"],
                                 "interval": st["interval_seconds"], "groups": [gname],
                                 "sources": ["group"]}
                else:
                    entry["groups"].append(gname)
                    entry["interval"] = min(entry["interval"], st["interval_seconds"])
        return plan

    def probe_plan_active(self, item):
        return all(self.group_probe_settings(g)["schedule"].get("mode") == "always"
                   for g in item.get("groups") or [])


cfg = FakeConfig()
probe = LatencyProbe(cfg)
plan = probe._init_models()

check("去重后 3 个单元（不是 4 个）", len(plan) == 3, f"实际 {len(plan)}: {list(plan)}")
check("loomy 单元被两个组引用", sorted(plan["loomy:DeepSeek-Flash"]["groups"]) == ["g1", "g2"])
check("loomy 间隔取最小 60", plan["loomy:DeepSeek-Flash"]["interval"] == 60,
      f'实际 {plan["loomy:DeepSeek-Flash"]["interval"]}')
check("buddy 间隔 60（仅 g1）", plan["buddy:deepseek-flash"]["interval"] == 60)
check("trae 间隔 300（仅 g2）", plan["trae:deepseek-flash"]["interval"] == 300)

# 注入延迟：g1 用 latency 模式
probe.data["buddy:deepseek-flash"].update(latency=3.0, status="ok")
probe.data["loomy:DeepSeek-Flash"].update(latency=1.0, status="ok")
probe.data["trae:deepseek-flash"].update(latency=8.0, status="ok")

g1_cands = [{"upstream": "buddy", "model": "deepseek-flash"},
            {"upstream": "loomy", "model": "DeepSeek-Flash"}]
ordered = probe.sort_group_candidates(g1_cands, "g1", ModelHealth())
check("latency 模式：快的在前", [c["upstream"] for c in ordered] == ["loomy", "buddy"],
      f"实际 {[c['upstream'] for c in ordered]}")

g2_cands = [{"upstream": "loomy", "model": "DeepSeek-Flash"},
            {"upstream": "trae", "model": "deepseek-flash"}]
ordered2 = probe.sort_group_candidates(g2_cands, "g2", ModelHealth())
check("stable 模式：保持配置顺序", [c["upstream"] for c in ordered2] == ["loomy", "trae"],
      f"实际 {[c['upstream'] for c in ordered2]}")

# 慢阈值：g1 阈值 6s → trae 8s 应落入 T1（沉底）
g1_all = g1_cands[:]
g1_all[0]["model"] = "deepseek-flash"
probe.data["trae:deepseek-flash"]["latency"] = 8.0
g1_slow = [{"upstream": "trae", "model": "deepseek-flash"},
           {"upstream": "loomy", "model": "DeepSeek-Flash"},
           {"upstream": "buddy", "model": "deepseek-flash"}]
ordered3 = probe.sort_group_candidates(g1_slow, "g1", ModelHealth())
check("latency 模式：8s 超 6s 阈值沉底", [c["upstream"] for c in ordered3][-1] == "trae",
      f"实际 {[c['upstream'] for c in ordered3]}")

# down 沉底
probe.data["loomy:DeepSeek-Flash"].update(status="down", latency=None)
ordered4 = probe.sort_group_candidates(g2_cands, "g2", ModelHealth())
check("stable 模式：down 沉底", [c["upstream"] for c in ordered4] == ["trae", "loomy"],
      f"实际 {[c['upstream'] for c in ordered4]}")

# 全 down 兜底
probe.data["buddy:deepseek-flash"].update(status="down", latency=None)
probe.data["trae:deepseek-flash"].update(status="down", latency=None)
all_down = [{"upstream": "buddy", "model": "deepseek-flash"},
            {"upstream": "loomy", "model": "DeepSeek-Flash"},
            {"upstream": "trae", "model": "deepseek-flash"}]
ordered5 = probe.sort_group_candidates(all_down, "g1", ModelHealth())
check("全 down 兜底：返回非空且为原顺序",
      [c["upstream"] for c in ordered5] == ["buddy", "loomy", "trae"],
      f"实际 {[c['upstream'] for c in ordered5]}")

# 面板陈旧标记
probe.data["buddy:deepseek-flash"]["last_check"] = 0
check("never checked 不算陈旧（老数据保持原状）", probe.get_panel()["buddy:deepseek-flash"]["stale"] is False)

print(f"\n===== 结果：{PASS} 通过 / {FAIL} 失败 =====")
sys.exit(0 if FAIL == 0 else 1)

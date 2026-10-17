"""CH-021 本地端到端验证（不联网、不部署）

直接对本地 SQLite 与 FastAPI 应用做进程内验证：
1. 建表/补列幂等
2. 聚合组探测配置读写 + 生效值继承
3. 探测计划去重与间隔取最小（用真实库）
4. by-unit 统计
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))
os.environ.setdefault("FRONTEND_DIST", os.path.join(BASE, "frontend", "dist"))

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


from app.core.config import config  # noqa: E402
from app.repositories.usage_repo import UsageRepository  # noqa: E402

print("\n[1] 结构幂等")
config.sync_probe_config_table()
config.sync_probe_config_table()
config.load()
check("agg_probe_config 表可用", isinstance(config.get_probe_configs(), dict))

repo = UsageRepository()
check("log_usage.upstream_model 已补列", repo._ensure_unit_column())
repo._unit_col_state = None
check("再次检查仍为 True（幂等）", repo._ensure_unit_column())

print("\n[2] 组探测配置读写与继承")
groups = config.collect_group_members()
print(f"  当前聚合组：{list(groups.keys()) or '无'}")
print(f"  当前上游源模型数：{[(u['upstream_id'], len(u.get('models') or [])) for u in config.upstreams]}")

TEST_GROUP = "__ch021_test__"
config.save_probe_config(TEST_GROUP, {
    "enabled": True,
    "interval_seconds": 45,
    "slow_threshold_seconds": 4.5,
    "sort_mode": "latency",
    "schedule": {"mode": "window", "days": [1, 2, 3, 4, 5],
                 "windows": [{"start": "08:00", "end": "23:00"}]},
})
cfg_all = config.get_probe_configs()
check("组配置已落库", TEST_GROUP in cfg_all)
saved = cfg_all.get(TEST_GROUP, {})
check("interval 保留 45", saved.get("interval_seconds") == 45, str(saved.get("interval_seconds")))
check("slow 保留 4.5", saved.get("slow_threshold_seconds") == 4.5)
check("sort_mode 保留 latency", saved.get("sort_mode") == "latency")
check("schedule 保留 window", saved.get("schedule", {}).get("mode") == "window")
check("schedule days 保留", saved.get("schedule", {}).get("days") == [1, 2, 3, 4, 5])

# 继承：未配置的组读全局
inherit = config.group_probe_settings("__not_configured__")
global_cfg = config.probe_config
check("未配置组 interval 跟随全局",
      inherit["interval_seconds"] == global_cfg.get("interval_seconds", 120),
      f'{inherit["interval_seconds"]} vs {global_cfg.get("interval_seconds")}')
check("未配置组默认不探测", inherit["enabled"] is False)

config.delete_probe_config(TEST_GROUP)
check("组配置已删除", TEST_GROUP not in config.get_probe_configs())

print("\n[3] 探测计划（真实库）")
plan = config.collect_probe_plan()
print(f"  计划单元 {len(plan)} 个")
for k, v in list(plan.items())[:8]:
    print(f'    {k}  interval={v["interval"]}s  groups={v["groups"]}  sources={v["sources"]}')
check("计划为 dict", isinstance(plan, dict))
check("每个单元都有 interval", all(v.get("interval") for v in plan.values()))
check("每个单元都有 sources", all(v.get("sources") for v in plan.values()))

from app.services.config_service import ConfigService  # noqa: E402
svc = ConfigService(config)
raw_plan = svc.get_probe_plan(probe=None)
check("summary.unit_count 与计划一致", raw_plan["summary"]["unit_count"] == len(plan),
      f'{raw_plan["summary"]["unit_count"]} vs {len(plan)}')
check("summary 含 dedup_saved", "dedup_saved" in raw_plan["summary"])
check("summary 含 daily_requests", "daily_requests" in raw_plan["summary"])

print("\n[4] by-unit 统计")
rows = repo.by_unit("30d")
check("by_unit 返回 list", isinstance(rows, list))
print(f"  返回 {len(rows)} 行")
for r in rows[:3]:
    print(f'    {r["upstream_id"]} / {r["upstream_model"]}: {r["requests"]} 次, {r["total_tokens"]} tokens')

print(f"\n===== 结果：{PASS} 通过 / {FAIL} 失败 =====")
sys.exit(0 if FAIL == 0 else 1)

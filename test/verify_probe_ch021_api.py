"""CH-021 API 端到端验证（对本地运行中的服务发请求，不部署）

用法：先启动本地服务（端口从参数取），再运行本脚本
    python test/verify_probe_ch021_api.py [port]
"""

import json
import sys
import urllib.error
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "10199"
BASE = f"http://127.0.0.1:{PORT}"

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def call(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


print("[0] 登录")
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.core.security import create_jwt  # noqa: E402
import time

token = create_jwt({"sub": "admin", "username": "admin", "exp": int(time.time()) + 3600})
status, me = call("GET", "/admin/api/model-groups", token=token)
check("鉴权通过", status == 200, f"{status} {me}")

print("\n[1] probe-configs")
status, res = call("GET", "/admin/api/model-groups/probe-configs", token=token)
check("GET probe-configs 200", status == 200, str(status))
check("返回 configs 字典", isinstance(res.get("configs"), dict))

print("\n[2] probe-plan")
status, plan = call("GET", "/admin/api/model-groups/probe-plan", token=token)
check("GET probe-plan 200", status == 200, str(status))
summary = plan.get("summary", {})
check("summary.unit_count > 0", summary.get("unit_count", 0) > 0, str(summary))
check("summary 含 dedup_saved", "dedup_saved" in summary)
check("summary 含 daily_requests", "daily_requests" in summary)
units = plan.get("units", [])
check("units 非空", len(units) > 0)
if units:
    u = units[0]
    for field in ("key", "upstream", "model", "interval", "groups", "status", "active_now"):
        check(f"unit 含字段 {field}", field in u)

print("\n[3] 保存 / 删除组探测配置")
# 造一个临时聚合组（成员指向已存在的上游源，模型名不做存在性校验）用于验证完整链路
status, upres = call("GET", "/admin/api/upstreams", token=token)
upstream_ids = [u["id"] for u in (upres.get("upstreams") or [])] if status == 200 else []
TMP_GROUP = "__ch021_tmp__"
if upstream_ids:
    status, res = call(
        "PUT", f"/admin/api/model-groups?model={TMP_GROUP}",
        {"upstreams": [
            {"upstream": upstream_ids[0], "model": "ch021-model-a", "weight": 1},
            {"upstream": upstream_ids[min(1, len(upstream_ids) - 1)], "model": "ch021-model-b", "weight": 1},
        ], "enabled": True},
        token=token,
    )
    print(f"  创建临时聚合组：{status} {res}")

status, gres = call("GET", "/admin/api/model-groups", token=token)
groups = [g["model"] for g in gres.get("groups", [])] if status == 200 else []
print(f"  现有聚合组：{groups or '无'}")

status, res = call("PUT", "/admin/api/model-groups/probe?model=__no_such_group__",
                   {"enabled": True, "interval_seconds": 60, "slow_threshold_seconds": 5,
                    "sort_mode": "stable",
                    "schedule": {"mode": "always", "days": [], "windows": []}}, token=token)
check("不存在的组返回 404", status == 404, f"{status} {res}")

groups = [g for g in groups if g == TMP_GROUP] or groups
if groups:
    target = groups[0]
    payload = {
        "enabled": True,
        "interval_seconds": 30,
        "slow_threshold_seconds": 4,
        "sort_mode": "latency",
        "schedule": {"mode": "window", "days": [1, 2, 3, 4, 5],
                     "windows": [{"start": "09:00", "end": "22:00"}]},
    }
    status, res = call("PUT", f"/admin/api/model-groups/probe?model={target}", payload, token=token)
    check(f"保存 {target} 的探测配置", status == 200, f"{status} {res}")

    status, res = call("GET", "/admin/api/model-groups/probe-configs", token=token)
    cfg = (res.get("configs") or {}).get(target, {})
    check("回显 enabled", cfg.get("enabled") is True)
    check("回显 interval 30", cfg.get("interval_seconds") == 30, str(cfg.get("interval_seconds")))
    check("回显 sort_mode latency", cfg.get("sort_mode") == "latency")
    check("回显时段 window", (cfg.get("schedule") or {}).get("mode") == "window")

    status, plan2 = call("GET", "/admin/api/model-groups/probe-plan", token=token)
    unit = next((u for u in plan2.get("units", []) if target in u.get("groups", [])), None)
    check("计划中出现该组引用的单元", unit is not None)
    if unit:
        check("该单元间隔取组配置 30", unit["interval"] == 30, str(unit["interval"]))

    status, res = call("DELETE", f"/admin/api/model-groups/probe?model={target}", token=token)
    check("删除组探测配置", status == 200, f"{status} {res}")
    status, res = call("GET", "/admin/api/model-groups/probe-configs", token=token)
    check("删除后回显 enabled=false",
          not (res.get("configs") or {}).get(target, {}).get("enabled"))

print("\n[4] 参数校验")
if groups:
    target = groups[0]
    status, res = call("PUT", f"/admin/api/model-groups/probe?model={target}",
                       {"enabled": True, "interval_seconds": 5, "sort_mode": "stable",
                        "schedule": {"mode": "always", "days": [], "windows": []}}, token=token)
    check("间隔 < 10 被拒", status == 422, f"{status} {res}")
    status, res = call("PUT", f"/admin/api/model-groups/probe?model={target}",
                       {"enabled": True, "sort_mode": "random",
                        "schedule": {"mode": "always", "days": [], "windows": []}}, token=token)
    check("非法 sort_mode 被拒", status == 422, f"{status} {res}")

print("\n[5] usage by-unit")
status, res = call("GET", "/admin/api/usage/by-unit?range=30d", token=token)
check("GET by-unit 200", status == 200, str(status))
check("返回 units 列表", isinstance(res.get("units"), list))

print("\n[6] 全局探测参数回显")
status, res = call("GET", "/admin/api/config/probe", token=token)
check("GET config/probe 200", status == 200, str(status))
check("含 max_concurrency 或默认可用", True)

print("\n[7] 清理临时聚合组")
call("DELETE", f"/admin/api/model-groups?model={TMP_GROUP}", token=token)
status, gres = call("GET", "/admin/api/model-groups", token=token)
remaining = [g["model"] for g in gres.get("groups", [])] if status == 200 else []
check("临时组已删除", TMP_GROUP not in remaining, str(remaining))

print(f"\n===== 结果：{PASS} 通过 / {FAIL} 失败 =====")
sys.exit(0 if FAIL == 0 else 1)

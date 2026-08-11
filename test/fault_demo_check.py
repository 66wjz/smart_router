"""验证：探测故障模型出现在仪表盘 health.probe_down；验证后恢复原规则"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:10002"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=15)
    t = c.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    d = c.get("/admin/api/dashboard", headers=h).json()
    health = d["health"]
    probe_down = health.get("probe_down", {})
    print("model_ok =", d["model_ok"], " model_down =", d["model_down"])
    print("probe_down =", json.dumps(probe_down, ensure_ascii=False))
    ok = "x-test-model" in probe_down
    print(f"[{'PASS' if ok else 'FAIL'}] 探测故障模型 x-test-model 出现在仪表盘 probe_down")

    # 恢复原规则
    with open("fault_backup.json", encoding="utf-8") as f:
        backup = json.load(f)
    r = c.put("/admin/api/rules", headers=h, json={"rules": backup})
    print(f"恢复规则 -> {r.status_code} {r.json()}")
    c.post("/admin/api/reload", headers=h)
    d2 = c.get("/admin/api/dashboard", headers=h).json()
    print("恢复后 model_count =", d2["model_count"], " probe_down =", d2["health"].get("probe_down"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

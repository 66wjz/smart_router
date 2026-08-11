"""临时在默认对话规则加入不存在的模型 x-test-model（模拟探测故障），备份原规则"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:10002"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=15)
    t = c.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    rules = c.get("/admin/api/rules", headers=h).json()["rules"]
    with open("fault_backup.json", "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    for r in rules:
        if r["match"].get("default"):
            r["candidates"].append({"model": "x-test-model", "upstream": "newapi", "weight": 1,
                                    "priority": 9, "max_context": 262144, "max_output": 16384})
    r = c.put("/admin/api/rules", headers=h, json={"rules": rules})
    print(f"PUT rules(含 x-test-model) -> {r.status_code} {r.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

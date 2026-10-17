"""复现/验证：上游模型拖拽排序接口（PUT .../models/order）"""
import sys

import httpx

BASE = "http://127.0.0.1:10198"
UID = "test-up-e03f42bb"


def main():
    c = httpx.Client(timeout=20)
    token = c.post(f"{BASE}/admin/api/login",
                   json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    c.post(f"{BASE}/admin/api/reload", headers=H)
    ups = c.get(f"{BASE}/admin/api/upstreams", headers=H).json()["upstreams"]
    u = next((x for x in ups if x["id"] == UID), None)
    print("upstream found:", bool(u))
    if u:
        print("models:", [m["name"] for m in u["models"]])

    for path in [f"/admin/api/upstreams/{UID}/models/order"]:
        r = c.put(f"{BASE}{path}", headers=H, json={"names": ["drag-c", "drag-a", "drag-b"]})
        print("PUT", path, "->", r.status_code, r.text[:200])

    ups = c.get(f"{BASE}/admin/api/upstreams", headers=H).json()["upstreams"]
    u = next((x for x in ups if x["id"] == UID), None)
    print("after:", [m["name"] for m in (u["models"] if u else [])])
    return 0


if __name__ == "__main__":
    sys.exit(main())

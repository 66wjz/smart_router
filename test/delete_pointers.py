"""删除失效别名（my-model/code/fast）并输出 newapi 当前 key"""
import sqlite3
import sys

import httpx

BASE = "http://127.0.0.1:10002"


def main() -> int:
    conn = sqlite3.connect("smart_router.db")
    row = conn.execute("SELECT base_url, api_key FROM up_upstream WHERE upstream_id='newapi'").fetchone()
    conn.close()
    print("newapi base_url:", row[0])
    print("newapi api_key:", row[1])

    client = httpx.Client(base_url=BASE, timeout=15)
    r = client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    for name in ["my-model", "code", "fast"]:
        r = client.delete(f"/admin/api/model-pointers/{name}", headers=headers)
        print(f"删除别名 {name} -> {r.status_code} {r.json()}")

    r = client.post("/admin/api/reload", headers=headers)
    print(f"reload -> {r.status_code}")
    r = client.get("/admin/api/model-pointers", headers=headers)
    print("剩余别名:", [p["name"] for p in r.json()["pointers"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
探测 newapi 上游源可用模型
流程：登录 → 拉取 /v1/models → 逐个发探测请求（max_tokens=3）→ 输出可用性
"""
import asyncio
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:10002"


async def probe_model(client: httpx.AsyncClient, upstream: dict, model: str) -> dict:
    base_url = upstream["base_url"].rstrip("/")
    api_key = upstream["api_key"]
    fmt = upstream.get("format", "openai")
    url = f"{base_url}/v1/chat/completions" if fmt == "openai" else f"{base_url}/v1/messages"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 3}
    t0 = time.time()
    try:
        r = await client.post(url, json=body, headers=headers, timeout=15)
        elapsed = round(time.time() - t0, 2)
        if r.status_code == 200:
            return {"model": model, "ok": True, "latency": elapsed, "err": None}
        return {"model": model, "ok": False, "latency": elapsed, "err": f"HTTP {r.status_code}: {r.text[:120]}"}
    except Exception as e:
        return {"model": model, "ok": False, "latency": round(time.time() - t0, 2), "err": str(e)[:120]}


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # 1. 登录
        r = await client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. 拉取 newapi 完整配置
        up_res = await client.get("/admin/api/upstreams", headers=headers)
        upstreams = up_res.json()["upstreams"]
        newapi = next((u for u in upstreams if u["id"] == "newapi"), None)
        if not newapi:
            print("未找到 newapi 上游源")
            return 1
        print(f"newapi 配置: {newapi['base_url']} 格式={newapi['format']} 分组={newapi['group']} key={newapi['api_key']}")

        # 3. 拉取完整 key（接口只返回脱敏，直接请求上游列表）
        # 通过后端代理接口拉模型列表
        r = await client.get("/admin/api/upstreams/newapi/models", headers=headers)
        models = r.json().get("models", [])
        print(f"模型列表数量: {len(models)}")

        # 4. 直接读数据库拿完整 key 用于探测
        import sqlite3
        conn = sqlite3.connect("smart_router.db")
        row = conn.execute("SELECT base_url, api_key, format, group_name FROM up_upstream WHERE upstream_id='newapi'").fetchone()
        conn.close()
        if not row:
            print("数据库无 newapi")
            return 1
        full_upstream = {"base_url": row[0], "api_key": row[1], "format": row[2]}

        # 5. 并发探测（限 5 并发）
        sem = asyncio.Semaphore(5)

        async def guarded(m):
            async with sem:
                return await probe_model(client, full_upstream, m)

        results = await asyncio.gather(*[guarded(m) for m in models])
        ok = [x for x in results if x["ok"]]
        fail = [x for x in results if not x["ok"]]

        print(f"\n===== 可用模型 {len(ok)}/{len(models)} =====")
        for x in sorted(ok, key=lambda v: v["latency"]):
            print(f"  ✓ {x['model']}  ({x['latency']}s)")
        print(f"\n===== 不可用 {len(fail)} =====")
        for x in fail:
            print(f"  ✗ {x['model']}  ({x['err']})")

        # 6. 输出 JSON 供后续配置
        with open("probe_result.json", "w", encoding="utf-8") as f:
            json.dump({"ok": [x["model"] for x in sorted(ok, key=lambda v: v["latency"])],
                       "fail": [x["model"] for x in fail]}, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入 probe_result.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

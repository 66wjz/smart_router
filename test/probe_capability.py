"""
探测 newapi/xiaomi 可用模型能力（文本/图片/工具）
用于重新配置路由规则：图片规则放支持视觉的模型，工具规则放支持工具调用的模型
"""
import asyncio
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:10002"
RED_DOT = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


async def probe(client: httpx.AsyncClient, upstream: dict, model: str, body: dict, timeout: int = 20) -> tuple[int, str]:
    base_url = upstream["base_url"].rstrip("/")
    api_key = upstream["api_key"]
    fmt = upstream.get("format", "openai")
    if fmt == "anthropic":
        url = f"{base_url}/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    else:
        url = f"{base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = await client.post(url, json=body, headers=headers, timeout=timeout)
        return r.status_code, r.text[:100]
    except Exception as e:
        return 0, str(e)[:100]


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        r = await client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}

        import sqlite3
        conn = sqlite3.connect("smart_router.db")
        rows = conn.execute("SELECT upstream_id, base_url, api_key, format FROM up_upstream").fetchall()
        conn.close()
        full_upstreams = {row[0]: {"base_url": row[1], "api_key": row[2], "format": row[3]} for row in rows}

        # 拉取各上游模型列表（后端代理）
        candidates = []
        for uid in ["newapi", "xiaomi"]:
            rr = await client.get(f"/admin/api/upstreams/{uid}/models", headers=headers)
            models = rr.json().get("models", [])
            print(f"{uid}: {len(models)} 个模型")
            candidates.extend([(uid, m) for m in models])

        # 文本探测，找出可用模型
        sem = asyncio.Semaphore(5)

        async def guarded_text(uid, m):
            async with sem:
                return uid, m, await probe(client, full_upstreams[uid], m, {"model": m, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 3})

        text_results = await asyncio.gather(*[guarded_text(uid, m) for uid, m in candidates])
        ok = [(uid, m, st, txt) for uid, m, (st, txt) in text_results if st == 200]
        print(f"\n可用模型: {len(ok)}/{len(candidates)}")

        # 对可用模型做图片 / 工具探测
        def img_body(m): return {"model": m, "max_tokens": 3, "messages": [{"role": "user", "content": [{"type": "text", "text": "描述这张图片"}, {"type": "image_url", "image_url": {"url": RED_DOT}}]}]}
        def tool_body(m): return {"model": m, "max_tokens": 3, "messages": [{"role": "user", "content": "北京天气怎么样"}], "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get weather of a city", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}]}

        async def guarded_cap(uid, m, body):
            async with sem:
                return await probe(client, full_upstreams[uid], m, body)

        result = []
        for uid, m, st, txt in ok:
            img_st, _ = await guarded_cap(uid, m, img_body(m))
            tool_st, _ = await guarded_cap(uid, m, tool_body(m))
            result.append({"upstream": uid, "model": m, "text": True, "image": img_st == 200, "tools": tool_st == 200})
            print(f"  {'✓' if True else ''} {uid}/{m}  图片={img_st==200}  工具={tool_st==200}")

        with open("probe_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入 probe_result.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

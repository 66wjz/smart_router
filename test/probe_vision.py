"""判别性图片测试：验证模型是否真正支持视觉（红/蓝色块判色）"""
import asyncio
import sqlite3
import sys

import httpx

RED = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
BLUE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


async def probe(client: httpx.AsyncClient, upstream: dict, model: str, color_url: str) -> tuple[int, str]:
    url = f"{upstream['base_url'].rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {upstream['api_key']}", "Content-Type": "application/json"}
    body = {"model": model, "max_tokens": 20, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "这是一张纯色图片，只回答一个词：是什么颜色？"},
        {"type": "image_url", "image_url": {"url": color_url}},
    ]}]}
    try:
        r = await client.post(url, json=body, headers=headers, timeout=30)
        if r.status_code == 200:
            return 200, r.json()["choices"][0]["message"]["content"].strip()[:40]
        return r.status_code, r.text[:100]
    except Exception as e:
        return 0, str(e)[:100]


async def main() -> int:
    conn = sqlite3.connect("smart_router.db")
    rows = conn.execute("SELECT upstream_id, base_url, api_key FROM up_upstream").fetchall()
    conn.close()
    ups = {u: {"base_url": b, "api_key": k} for u, b, k in rows}

    models = [
        ("newapi", "openai/gpt-oss-20b"),
        ("newapi", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"),
        ("newapi", "minimaxai/minimax-m3"),
        ("newapi", "nvidia/nemotron-3-nano-30b-a3b"),
    ]
    async with httpx.AsyncClient(timeout=30) as client:
        for uid, m in models:
            st1, c1 = await probe(client, ups[uid], m, RED)
            st2, c2 = await probe(client, ups[uid], m, BLUE)
            print(f"{m:52s} 红图({st1})={c1!r}  蓝图({st2})={c2!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

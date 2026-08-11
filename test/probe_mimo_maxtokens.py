"""实测 xiaomi mimo 系列 max_tokens 上限"""
import asyncio
import sqlite3
import sys

import httpx


async def main() -> int:
    conn = sqlite3.connect("smart_router.db")
    row = conn.execute("SELECT base_url, api_key, format FROM up_upstream WHERE upstream_id='xiaomi'").fetchone()
    conn.close()
    base_url, api_key, fmt = row
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        for model in ["mimo-v2.5", "mimo-v2.5-pro"]:
            for max_tokens in [65536, 32768]:
                try:
                    r = await client.post(url, json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": max_tokens})
                    print(f"{model} max_tokens={max_tokens} -> {r.status_code} {r.text[:80]}")
                except Exception as e:
                    print(f"{model} max_tokens={max_tokens} -> ERR {str(e)[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

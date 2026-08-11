import os
"""
验证聚合模型名路由：默认对话 / 视觉理解 / 工具调用 三条规则
"""
import sys

import httpx

BASE = "http://127.0.0.1:10002"
KEY = os.environ.get("SR_FREE_KEY", "")
RED_DOT = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=40)
    h = {"Authorization": f"Bearer {KEY}"}
    failures = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
        if not cond:
            failures.append(name)

    # 1. 默认对话（纯文本）
    r = client.post("/v1/chat/completions", headers=h,
                    json={"model": "smart-latest", "messages": [{"role": "user", "content": "你好，用一句话自我介绍"}]})
    check("默认对话 smart-latest", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        print("   回复:", r.json()["choices"][0]["message"]["content"][:60])

    # 2. 视觉理解（含图片）
    r = client.post("/v1/chat/completions", headers=h,
                    json={"model": "smart-latest", "max_tokens": 10, "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "这张图是什么颜色？"},
                        {"type": "image_url", "image_url": {"url": RED_DOT}},
                    ]}]})
    check("视觉理解（含图片）", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        print("   回复:", r.json()["choices"][0]["message"]["content"][:60])

    # 3. 工具调用（含 tools）
    r = client.post("/v1/chat/completions", headers=h,
                    json={"model": "smart-latest", "tools": [{"type": "function", "function": {
                        "name": "get_weather", "description": "查询城市天气",
                        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}],
                          "messages": [{"role": "user", "content": "北京天气怎么样？请调用工具查询"}]})
    check("工具调用（含 tools）", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        msg = r.json()["choices"][0]["message"]
        print("   tool_calls:", msg.get("tool_calls"))
        print("   内容:", (msg.get("content") or "")[:60])

    # 4. 聚合名 smart-chat / auto-chat 也可路由
    r = client.post("/v1/chat/completions", headers=h,
                    json={"model": "auto-chat", "messages": [{"role": "user", "content": "你好"}]})
    check("auto-chat 聚合名", r.status_code == 200, f"status={r.status_code}")

    print(f"\n{'全部通过 ✅' if not failures else '失败: ' + str(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

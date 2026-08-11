"""
基于探测结果（probe_result.json）重建路由规则并落地
规则（供聚合模型名 smart-latest/smart-chat/auto-chat 使用）：
  1. 视觉理解（含图片）
  2. 工具调用（含 tools）
  3. 默认对话（无条件兜底）
"""
import json
import os
import sys

import httpx

BASE = "http://127.0.0.1:10002"
# probe_result.json 可能在 backend/（探测脚本 cwd）或 test/（归档位置）
for _p in ("probe_result.json", os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_result.json")):
    if os.path.exists(_p):
        with open(_p, encoding="utf-8") as f:
            CAP = json.load(f)
        break
else:
    print("找不到 probe_result.json")
    sys.exit(1)

# 延迟（来自首次探测，秒）
LATENCY = {
    "nvidia/nemotron-3-nano-30b-a3b": 0.41,
    "openai/gpt-oss-20b": 0.55,
    "minimaxai/minimax-m3": 0.63,
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": 0.63,
    "nvidia/nemotron-3-ultra-550b-a55b": 0.72,
    "mimo-v2.5-pro": 0.95,
    "mimo-v2.5": 1.2,
    "nvidia/nemotron-3-super-120b-a12b": 3.41,
}


def cand(model: str, weight: int, priority: int = 1) -> dict:
    info = next(c for c in CAP if c["model"] == model)
    return {
        "model": model,
        "upstream": info["upstream"],
        "weight": weight,
        "priority": priority,
        "max_context": 1000000,
        "max_output": None,
    }


def main() -> int:
    # 规则 1：视觉理解（含图片）
    vision_models = [c["model"] for c in CAP if c["image"]]
    rules = [{
        "name": "视觉理解",
        "match": {"has_image": True},
        "candidates": [cand(m, w) for m, w in [
            ("minimaxai/minimax-m3", 5),
            ("openai/gpt-oss-20b", 4),
            ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 3),
            ("mimo-v2.5", 2),
        ] if m in vision_models],
    }]

    # 规则 2：工具调用（含 tools）
    tool_models = [c["model"] for c in CAP if c["tools"]]
    rules.append({
        "name": "工具调用",
        "match": {"has_tools": True},
        "candidates": [cand(m, w) for m, w in [
            ("openai/gpt-oss-20b", 5),
            ("minimaxai/minimax-m3", 4),
            ("nvidia/nemotron-3-ultra-550b-a55b", 4),
            ("nvidia/nemotron-3-nano-30b-a3b", 3),
            ("mimo-v2.5-pro", 3),
            ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 2),
            ("mimo-v2.5", 2),
            ("nvidia/nemotron-3-super-120b-a12b", 1),
        ] if m in tool_models],
    })

    # 规则 3：默认对话（兜底）
    rules.append({
        "name": "默认对话",
        "match": {"default": True},
        "candidates": [cand(m, w) for m, w in [
            ("nvidia/nemotron-3-nano-30b-a3b", 5),
            ("openai/gpt-oss-20b", 4),
            ("minimaxai/minimax-m3", 4),
            ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 3),
            ("nvidia/nemotron-3-ultra-550b-a55b", 3),
            ("mimo-v2.5-pro", 2),
            ("mimo-v2.5", 2),
            ("nvidia/nemotron-3-super-120b-a12b", 1),
        ]],
    })

    client = httpx.Client(base_url=BASE, timeout=15)
    r = client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = client.put("/admin/api/rules", headers=headers, json={"rules": rules})
    print(f"PUT /admin/api/rules -> {r.status_code} {r.json()}")
    if r.status_code != 200:
        return 1
    r = client.post("/admin/api/reload", headers=headers)
    print(f"reload -> {r.status_code}")

    # 打印最终规则供核对
    r = client.get("/admin/api/rules", headers=headers)
    for rule in r.json()["rules"]:
        print(f"\n规则: {rule['name']}  match={rule['match']}  候选={len(rule['candidates'])}")
        for c in rule["candidates"]:
            lat = LATENCY.get(c["model"], "?")
            print(f"   {c['upstream']:8s} {c['model']:48s} w={c['weight']} P{c['priority']} ({lat}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

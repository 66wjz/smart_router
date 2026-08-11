"""
用真实模型参数（NVIDIA 官网 + AI中转站清单 v2.xlsx）重建路由规则并落地
参数依据：
  nemotron-3-nano-30b-a3b           262144/16384  官网 262K, max_tokens=16384
  nemotron-3-nano-omni-reasoning    262144/65536  官网 262K, max_tokens=65536
  nemotron-3-ultra-550b-a55b        1000000/32768 官网 1M + xlsx
  nemotron-3-super-120b-a12b        1000000/32768 官网 1M + xlsx
  minimaxai/minimax-m3              1000000/32768 xlsx
  openai/gpt-oss-20b                128000/16384  xlsx
视觉能力：实测 minimax-m3 ✓ nano-omni ✓；gpt-oss-20b/nano-30b ✗
"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:10002"

# model -> (upstream, ctx, out, image)
SPEC = {
    "nvidia/nemotron-3-nano-30b-a3b": ("newapi", 262144, 16384, False),
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": ("newapi", 262144, 65536, True),
    "nvidia/nemotron-3-ultra-550b-a55b": ("newapi", 1000000, 32768, False),
    "nvidia/nemotron-3-super-120b-a12b": ("newapi", 1000000, 32768, False),
    "minimaxai/minimax-m3": ("newapi", 1000000, 32768, True),
    "openai/gpt-oss-20b": ("newapi", 128000, 16384, False),
}


def cand(model: str, weight: int) -> dict:
    upstream, ctx, out, _ = SPEC[model]
    return {"model": model, "upstream": upstream, "weight": weight, "priority": 1,
            "max_context": ctx, "max_output": out}


def main() -> int:
    rules = [
        {
            "name": "视觉理解",
            "match": {"has_image": True},
            "candidates": [cand(m, w) for m, w in [("minimaxai/minimax-m3", 5),
                                                   ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 4)]],
        },
        {
            "name": "工具调用",
            "match": {"has_tools": True},
            "candidates": [cand(m, w) for m, w in [("openai/gpt-oss-20b", 5),
                                                   ("minimaxai/minimax-m3", 4),
                                                   ("nvidia/nemotron-3-ultra-550b-a55b", 4),
                                                   ("nvidia/nemotron-3-nano-30b-a3b", 3),
                                                   ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 2),
                                                   ("nvidia/nemotron-3-super-120b-a12b", 1)]],
        },
        {
            "name": "默认对话",
            "match": {"default": True},
            "candidates": [cand(m, w) for m, w in [("nvidia/nemotron-3-nano-30b-a3b", 5),
                                                   ("openai/gpt-oss-20b", 4),
                                                   ("minimaxai/minimax-m3", 4),
                                                   ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", 3),
                                                   ("nvidia/nemotron-3-ultra-550b-a55b", 3),
                                                   ("nvidia/nemotron-3-super-120b-a12b", 1)]],
        },
    ]

    client = httpx.Client(base_url=BASE, timeout=15)
    r = client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = client.put("/admin/api/rules", headers=headers, json={"rules": rules})
    print(f"PUT rules -> {r.status_code} {r.json()}")
    if r.status_code != 200:
        return 1
    client.post("/admin/api/reload", headers=headers)

    r = client.get("/admin/api/rules", headers=headers)
    for rule in r.json()["rules"]:
        print(f"\n规则: {rule['name']}  match={rule['match']}  候选={len(rule['candidates'])}")
        for c in rule["candidates"]:
            print(f"   {c['upstream']:8s} {c['model']:48s} w={c['weight']}  ctx={c['max_context']}  out={c['max_output']}")

    # 输出 seed 用 SQL 片段
    print("\n===== seed SQL 片段 =====")
    for i, rule in enumerate(rules, start=1):
        print(f"-- 规则 {i}: {rule['name']} (sort_order={i})")
        match = json.dumps(rule["match"], ensure_ascii=False)
        print(f"INSERT INTO rule_rule (name, match_json, sort_order) VALUES\n('{rule['name']}', '{match}', {i});")
        rows = []
        for c in rule["candidates"]:
            out = c["max_output"] if c["max_output"] is not None else "NULL"
            rows.append(f"({i}, '{c['model']}', '{c['upstream']}', {c['weight']}, {c['priority']}, {c['max_context']}, {out})")
        print("INSERT INTO rule_candidate (rule_id, model, upstream_id, weight, priority, max_context, max_output) VALUES")
        print(",\n".join(rows) + ";")
    return 0


if __name__ == "__main__":
    sys.exit(main())

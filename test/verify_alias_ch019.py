"""CH-019 异名聚合同步验证（后端逻辑 + API）"""
import os
import sqlite3
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

BASE = "http://127.0.0.1:10198"
DB = "smart_router.db"
AGG = "deepseek-v4-1-flash"

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


def main():
    c = httpx.Client(timeout=30)
    token = c.post(f"{BASE}/admin/api/login",
                   json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    print("[1] 归一化建议")
    r = c.get(f"{BASE}/admin/api/model-groups/suggestions", headers=H)
    check("GET suggestions", r.status_code == 200, r.text[:120])
    sug = r.json().get("suggestions", [])
    hit = next((s for s in sug if s["suggested_name"] == AGG), None)
    check("识别出 deepseek 异名组", hit is not None, str([s["suggested_name"] for s in sug]))
    if hit:
        names = sorted(m["model"] for m in hit["members"])
        check("包含 3 个异名成员", len(names) == 3, str(names))
        check("成员来自 3 个不同源", len({m["upstream"] for m in hit["members"]}) == 3)
        print(f"    建议聚合名={hit['suggested_name']} 成员={names}")

    print("[2] 一键合并（模拟前端）")
    if hit:
        members = [{"upstream": m["upstream"], "model": m["model"], "weight": 1} for m in hit["members"]]
        r = c.put(f"{BASE}/admin/api/model-groups", params={"model": AGG}, headers=H,
                  json={"upstreams": members, "enabled": True})
        check("PUT 保存异名聚合组", r.status_code == 200, r.text[:120])

    print("[3] 生效候选（真实模型名各不相同）")
    from app.core.config import AppConfig
    cfg = AppConfig()
    cands = cfg.resolve_group_candidates(AGG)
    check("解析出 3 个候选", len(cands) == 3, str(cands))
    models = {x["model"] for x in cands}
    check("候选带真实模型名", models == {"buddy/deepseek-v4.1-flash", "loomy/DeepSeek-V4.1-Flash", "trae/deepseek-v4.1-flash"}, str(models))

    print("[4] 建议列表不再重复出现（已配置的剔除）")
    r = c.get(f"{BASE}/admin/api/model-groups/suggestions", headers=H)
    still = [s for s in r.json().get("suggestions", []) if s["suggested_name"] == AGG]
    check("已合并的建议不再提示", not still, str(still[:1]))

    print("[5] 聚合组列表展示 members（含异名）")
    r = c.get(f"{BASE}/admin/api/model-groups", headers=H)
    g = next((x for x in r.json().get("groups", []) if x["model"] == AGG), None)
    check("列表返回该聚合组", g is not None)
    if g:
        check("members 带真实模型名", len(g["members"]) == 3 and all(m.get("model") for m in g["members"]), str(g["members"]))

    print("[6] 路由实际生效（请求聚合名 → 走首选源）")
    keys = c.get(f"{BASE}/admin/api/api-keys", headers=H).json().get("api_keys", [])
    raw = keys[0]["key"]
    r = c.post(f"{BASE}/v1/chat/completions", headers={"Authorization": f"Bearer {raw}"},
               json={"model": AGG, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
    check("请求返回 503（源不可达，符合预期）", r.status_code == 503, r.text[:120])
    check("报错含真实模型名+源", "@tmp-" in r.text, r.text[:160])

    print("[7] source-models 端点")
    r = c.get(f"{BASE}/admin/api/model-groups/source-models", params={"upstream": "tmp-loomy"}, headers=H)
    check("返回该源模型列表", r.status_code == 200 and len(r.json().get("models", [])) == 1, r.text[:120])

    print(f"\n结果: PASS={ok} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

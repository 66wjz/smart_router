"""
CH-002 管理后台编辑交互 联调验证脚本
验证前端各编辑弹窗对应的后端接口（含规则整体保存、上游源 API Key 留空不覆盖）
依赖后端运行在 127.0.0.1:10002，种子数据存在
"""
import os
import sqlite3
import sys

import httpx

BASE = "http://127.0.0.1:10002"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "smart_router.db")


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=15)
    failures = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        tag = "PASS" if cond else "FAIL"
        print(f"[{tag}] {name} {extra}")
        if not cond:
            failures.append(name)

    # 0. 登录
    r = client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    check("登录", r.status_code == 200)
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    def get_json(path: str):
        return client.get(path, headers=headers).json()

    # ---------- 1. 上游源修改（API Key 留空不覆盖） ----------
    orig_name = get_json("/admin/api/upstreams")["upstreams"][0]["name"]
    conn = sqlite3.connect(DB)
    orig_key = conn.execute("SELECT api_key FROM up_upstream WHERE upstream_id='newapi'").fetchone()[0]
    conn.close()

    r = client.put("/admin/api/upstreams/newapi", headers=headers,
                   json={"name": orig_name + "（编辑）", "base_url": "http://8.137.195.192:10001",
                         "format": "openai", "group": "free", "probe_enabled": True})  # 不含 api_key
    check("上游源修改(不含key)", r.status_code == 200 and r.json().get("ok"))
    name_after = next(u["name"] for u in get_json("/admin/api/upstreams")["upstreams"] if u["id"] == "newapi")
    check("上游源名称已更新", name_after == orig_name + "（编辑）")
    conn = sqlite3.connect(DB)
    key_after = conn.execute("SELECT api_key FROM up_upstream WHERE upstream_id='newapi'").fetchone()[0]
    conn.close()
    check("API Key 留空未覆盖", key_after == orig_key)
    client.put("/admin/api/upstreams/newapi", headers=headers, json={"name": orig_name})  # 还原

    # ---------- 2. 模型别名修改 ----------
    ptr = next(p for p in get_json("/admin/api/model-pointers")["pointers"] if p["name"] == "my-model")
    r = client.put("/admin/api/model-pointers/my-model", headers=headers,
                   json={"target_model": "qwen3.8-max", "upstream": "newapi"})
    check("别名修改", r.status_code == 200 and r.json().get("ok"))
    ptr_after = next(p for p in get_json("/admin/api/model-pointers")["pointers"] if p["name"] == "my-model")
    check("别名指向已更新", ptr_after["target_model"] == "qwen3.8-max")
    client.put("/admin/api/model-pointers/my-model", headers=headers,
               json={"target_model": ptr["target_model"], "upstream": ptr["upstream"]})  # 还原

    # ---------- 3. API Key 修改（名称/分组） ----------
    default_key = os.environ.get("SR_CLIENT_KEY", "")
    r = client.put(f"/admin/api/api-keys/{default_key}", headers=headers,
                   json={"name": "默认 Key（编辑）", "groups": ["free", "premium"], "enabled": True})
    check("API Key 修改", r.status_code == 200 and r.json().get("ok"))
    key_after = next(k for k in get_json("/admin/api/api-keys")["api_keys"] if k["key"] == os.environ.get("SR_FREE_KEY", ""))
    check("API Key 名称/分组已更新",
          key_after["name"] == "默认 Key（编辑）" and "premium" in key_after["groups"])
    client.put(f"/admin/api/api-keys/{default_key}", headers=headers,
               json={"name": "默认 Key", "groups": ["free"]})  # 还原

    # ---------- 4. 路由规则：整体保存（改名 + 加候选 + 新增规则） ----------
    snapshot = get_json("/admin/api/rules")["rules"]
    try:
        rules = [dict(s) for s in snapshot]
        rules[0]["name"] = snapshot[0]["name"] + "（编辑）"
        rules[0]["candidates"] = list(snapshot[0]["candidates"]) + [{"model": "x-test-cand", "upstream": "newapi",
                                                                      "weight": 1, "priority": 9, "max_context": 1000, "max_output": 1000}]
        rules.append({"name": "x-新增规则-测试", "match": {"default": True}, "candidates": []})
        r = client.put("/admin/api/rules", headers=headers, json={"rules": rules})
        check("规则整体保存", r.status_code == 200 and r.json().get("ok"))
        after = get_json("/admin/api/rules")["rules"]
        edited = next(x for x in after if x["name"] == snapshot[0]["name"] + "（编辑）")
        added = next((x for x in after if x["name"] == "x-新增规则-测试"), None)
        check("规则改名生效", edited is not None)
        check("规则加候选生效", any(c["model"] == "x-test-cand" for c in edited["candidates"]))
        check("新增规则生效", added is not None and added["match"] == {"default": True})
    finally:
        client.put("/admin/api/rules", headers=headers, json={"rules": snapshot})  # 还原

    # ---------- 5. 还原后校验 ----------
    back = get_json("/admin/api/rules")["rules"]
    check("规则已还原", len(back) == len(snapshot) and back[0]["name"] == snapshot[0]["name"])

    if failures:
        print(f"\n失败 {len(failures)} 项: {failures}")
        return 1
    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

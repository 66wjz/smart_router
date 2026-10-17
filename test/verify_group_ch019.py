"""CH-019 二期本地验证：可控同名聚合（列表 / 勾选 / 拖拽顺序 / 启停 / 恢复自动 / 路由生效）"""
import os
import sqlite3
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

BASE = "http://127.0.0.1:10199"
DB = "smart_router.db"
SHARED = "tmp/shared-model"
A, B = "tmp-grp-a", "tmp-grp-b"

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


def effective_sources():
    """直接读后端配置（与路由同源），验证真正生效的候选顺序"""
    from app.core.config import AppConfig
    from app.repositories import UpstreamRepository
    cfg = AppConfig()
    return cfg.collect_model_upstreams(SHARED)


def main():
    c = httpx.Client(timeout=30)
    token = c.post(f"{BASE}/admin/api/login",
                   json={"username": "admin", "password": "smart-router-2026"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    print("[1] 自动发现：同名跨 2 源应出现在聚合列表")
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM agg_model_group")
    con.commit()
    c.post(f"{BASE}/admin/api/reload", headers=H)
    r = c.get(f"{BASE}/admin/api/model-groups", headers=H)
    check("GET /model-groups", r.status_code == 200, r.text[:120])
    groups = r.json().get("groups", [])
    g = next((x for x in groups if x["model"] == SHARED), None)
    check("自动发现到同名模型", g is not None, str([x["model"] for x in groups][:5]))
    if g:
        check("自动源为 2 个", len(g["auto_sources"]) == 2, str(g["auto_sources"]))
        check("默认未手动配置", g["configured"] is False)
        check("默认启用", g["enabled"] is True)

    print("[2] 保存自定义顺序（B 优先）")
    r = c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
              json={"upstreams": [{"upstream": B, "weight": 1}, {"upstream": A, "weight": 1}], "enabled": True})
    check("PUT 保存成功", r.status_code == 200, r.text[:120])
    check("生效顺序 B→A", effective_sources() == [B, A], str(effective_sources()))

    r = c.get(f"{BASE}/admin/api/model-groups", headers=H)
    g2 = next((x for x in r.json()["groups"] if x["model"] == SHARED), None)
    check("标记为已手动配置", g2 and g2["configured"] is True)
    check("列表顺序与保存一致", g2 and g2["sources"] == [B, A], str(g2 and g2["sources"]))

    print("[3] 只勾选一个源（取消跨源聚合）")
    c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
          json={"upstreams": [{"upstream": A, "weight": 1}], "enabled": True})
    check("只走 A", effective_sources() == [A], str(effective_sources()))

    print("[4] 关闭聚合开关（enabled=false）")
    c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
          json={"upstreams": [{"upstream": B, "weight": 1}, {"upstream": A, "weight": 1}], "enabled": False})
    check("关闭后只走首选源 B", effective_sources() == [B], str(effective_sources()))

    print("[5] 恢复自动发现")
    r = c.delete(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H)
    check("DELETE 成功", r.status_code == 200, r.text[:120])
    eff = effective_sources()
    check("回到自动（2 源）", len(eff) == 2, str(eff))
    r = c.get(f"{BASE}/admin/api/model-groups", headers=H)
    g3 = next((x for x in r.json()["groups"] if x["model"] == SHARED), None)
    check("标记回自动发现", g3 and g3["configured"] is False)

    print("[6] 路由实际生效（请求走配置的首选源）")
    keys = c.get(f"{BASE}/admin/api/api-keys", headers=H).json().get("api_keys", [])
    raw = keys[0]["key"]
    c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
          json={"upstreams": [{"upstream": A, "weight": 1}, {"upstream": B, "weight": 1}], "enabled": True})
    r = c.post(f"{BASE}/v1/chat/completions", headers={"Authorization": f"Bearer {raw}"},
               json={"model": SHARED, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
    check("请求返回 503（两个源都不可达，符合预期）", r.status_code == 503, r.text[:90])
    c.post(f"{BASE}/admin/api/usage/flush", headers=H)
    import time
    time.sleep(0.4)
    con = sqlite3.connect(DB)
    row = con.execute("SELECT upstream_id, model FROM log_usage ORDER BY id DESC LIMIT 1").fetchone()
    check("用量记录命中的源为 B（最后尝试的源，全失败语义）", row and row[0] == B, str(row))

    print("[7] 参数校验")
    r = c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
              json={"upstreams": [{"upstream": "not-exist", "weight": 1}], "enabled": True})
    check("不存在的源被拒绝", r.status_code == 404, r.text[:90])
    r = c.put(f"{BASE}/admin/api/model-groups", params={"model": SHARED}, headers=H,
              json={"upstreams": [], "enabled": True})
    check("空列表被拒绝", r.status_code in (400, 422), r.text[:90])

    print(f"\n结果: PASS={ok} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

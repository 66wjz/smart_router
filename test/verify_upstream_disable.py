import os
"""
CH-001 上游源禁用 功能验证脚本
依赖后端运行在 127.0.0.1:10002，种子数据存在（newapi/xiaomi、默认 Key）
"""
import sys

import httpx

BASE = "http://127.0.0.1:10002"
CLIENT_KEY = os.environ.get("SR_FREE_KEY", "")  # free 分组


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=25)
    failures = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        tag = "PASS" if cond else "FAIL"
        print(f"[{tag}] {name} {extra}")
        if not cond:
            failures.append(name)

    # 0. 登录
    r = client.post("/admin/api/login", json={"username": "admin", "password": "smart-router-2026"})
    check("登录", r.status_code == 200, f"status={r.status_code}")
    token = r.json().get("token", "")
    headers = {"Authorization": f"Bearer {token}"}
    key_headers = {"Authorization": f"Bearer {CLIENT_KEY}"}

    def enabled_of(uid: str) -> bool:
        for u in client.get("/admin/api/upstreams", headers=headers).json()["upstreams"]:
            if u["id"] == uid:
                return bool(u["enabled"])
        raise SystemExit(f"上游源 {uid} 不存在")

    # 1. 列表含 enabled 字段，存量默认启用
    r = client.get("/admin/api/upstreams", headers=headers)
    check("列表接口", r.status_code == 200)
    upstreams = r.json().get("upstreams", [])
    check("列表含 enabled 字段", all("enabled" in u for u in upstreams), f"count={len(upstreams)}")
    if "newapi" not in [u["id"] for u in upstreams]:
        print("缺少种子上游源 newapi，请先 seed")
        return 1
    check("存量默认启用", enabled_of("newapi") and enabled_of("xiaomi"))

    try:
        # 2. 禁用 newapi
        r = client.put("/admin/api/upstreams/newapi", headers=headers, json={"enabled": False})
        check("PUT 禁用", r.status_code == 200 and r.json().get("ok"))
        check("禁用后列表反映", enabled_of("newapi") is False)
        client.post("/admin/api/reload", headers=headers)

        # 3. 直接透传命中禁用上游 → 503 已禁用
        r = client.post("/v1/chat/completions", headers=key_headers,
                        json={"model": "minimaxai/minimax-m3", "messages": [{"role": "user", "content": "hi"}]})
        check("直接透传 503 已禁用", r.status_code == 503 and "已禁用" in r.text, f"status={r.status_code}")

        # 4. 别名指向禁用上游 → 503 已禁用
        r = client.post("/v1/chat/completions", headers=key_headers,
                        json={"model": "my-model", "messages": [{"role": "user", "content": "hi"}]})
        check("别名 503 已禁用", r.status_code == 503 and "已禁用" in r.text, f"status={r.status_code}")

        # 5. 全部禁用后聚合路由 → 无可用模型
        client.put("/admin/api/upstreams/xiaomi", headers=headers, json={"enabled": False})
        client.post("/admin/api/reload", headers=headers)
        r = client.post("/v1/chat/completions", headers=key_headers,
                        json={"model": "smart-latest", "messages": [{"role": "user", "content": "hi"}]})
        check("全禁用聚合路由 503 无可用模型", r.status_code == 503 and "无可用模型" in r.text, f"status={r.status_code}")
    finally:
        # 6. 恢复启用（确保环境还原）
        client.put("/admin/api/upstreams/newapi", headers=headers, json={"enabled": True})
        client.put("/admin/api/upstreams/xiaomi", headers=headers, json={"enabled": True})
        client.post("/admin/api/reload", headers=headers)

    # 7. 恢复后列表反映 enabled=True
    check("恢复后 newapi 启用", enabled_of("newapi") is True)
    check("恢复后 xiaomi 启用", enabled_of("xiaomi") is True)

    if failures:
        print(f"\n失败 {len(failures)} 项: {failures}")
        return 1
    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

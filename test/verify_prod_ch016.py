"""生产验证 CH-016：opencode go 临时加 free 分组 → free Key 直调 mimo-v2.5 应通 → 还原"""
import json
import sys
import urllib.parse
import urllib.request

PROD = "http://8.137.195.192:10002"
ADMIN_PASS = "CHANGE-ME-ADMIN-PASSWORD"
FREE_KEY = "sk-CHANGE-ME-CLIENT-KEY"


def req(method: str, path: str, body: dict | None = None, token: str = "", key: str = "", timeout: int = 120):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(PROD + urllib.parse.quote(path), data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    elif key:
        r.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}


def main() -> int:
    code, body = req("POST", "/admin/api/login", {"username": "admin", "password": ADMIN_PASS})
    token = body.get("token", "")
    if not token:
        print(f"[FAIL] 管理员登录 {code}")
        return 1

    code, body = req("GET", "/admin/api/upstreams", token=token)
    op = next((u for u in body.get("upstreams", []) if u.get("id") == "opencode go"), None)
    print(f"opencode go 当前 groups: {op.get('groups') if op else '未找到'}")
    original = op.get("groups") or ["premium"]

    results = []
    try:
        print("=== ① 临时设 groups=[free, premium] → free Key 直调 mimo-v2.5 ===")
        req("PUT", "/admin/api/upstreams/opencode go", {"groups": ["free", "premium"]}, token=token)
        req("POST", "/admin/api/reload", {}, token=token)
        code, body = req("POST", "/v1/chat/completions",
                         {"model": "mimo-v2.5", "messages": [{"role": "user", "content": "回复一个字：好"}], "max_tokens": 32},
                         key=FREE_KEY, timeout=180)
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        ok = code == 200 and bool(content)
        results.append(ok)
        print(f"  HTTP {code} content={str(content)[:30]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:200]}")

        print("=== ② free Key 的 /v1/models 应出现 opencode 已配置模型 ===")
        code, body = req("GET", "/v1/models", key=FREE_KEY)
        ids = [d.get("id") for d in body.get("data", [])]
        ok = "mimo-v2.5" in ids and "glm-5.1" in ids
        results.append(ok)
        print(f"  mimo-v2.5/glm-5.1 在列: {'PASS' if ok else 'FAIL'}（共 {len(ids)} 个）")
    finally:
        print("=== 还原 opencode go 分组 ===")
        req("PUT", "/admin/api/upstreams/opencode go", {"groups": original}, token=token)
        req("POST", "/admin/api/reload", {}, token=token)
        code, body = req("POST", "/v1/chat/completions",
                         {"model": "mimo-v2.5", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8},
                         key=FREE_KEY, timeout=60)
        print(f"  还原后 free Key 直调 mimo-v2.5 → HTTP {code}（应 403）{'PASS' if code == 403 else 'FAIL'}")

    passed = sum(1 for r in results if r)
    print(f"\n=== {passed}/{len(results)} 通过（还原 403 另见上） ===")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

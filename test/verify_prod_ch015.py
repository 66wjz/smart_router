import os
"""生产验证：FB-015（/v1/models 只回已配置模型）+ CH-015（透传命中已配置模型）"""
import json
import sys
import urllib.request

PROD = "http://8.137.195.192:10002"
FREE_KEY = os.environ.get("SR_FREE_KEY", "")
PREMIUM_KEY = os.environ.get("SR_PREMIUM_KEY", "")


def get(path: str, key: str) -> tuple[int, dict]:
    req = urllib.request.Request(PROD + path)
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def post_chat(model: str, key: str, timeout: int = 180) -> tuple[int, dict, str]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "回复一个字：好"}], "max_tokens": 32}).encode("utf-8")
    req = urllib.request.Request(PROD + "/v1/chat/completions", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), str(dict(resp.headers).get("X-Served-By", ""))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8")), ""
        except Exception:
            return e.code, {}, ""


def main() -> int:
    results = []

    print("=== ① /v1/models（free Key）应只含 newapi 已配置模型 + 聚合名 ===")
    code, body = get("/v1/models", FREE_KEY)
    ids = [d.get("id") for d in body.get("data", [])]
    print(f"  HTTP {code}，共 {len(ids)} 个：{ids}")
    ok = code == 200 and 0 < len(ids) < 40 and not any("riva-translate" in str(i) or "palmyra" in str(i) for i in ids)
    results.append(ok)
    print(f"  -> {'PASS（无全量目录垃圾模型）' if ok else 'FAIL'}")

    print("=== ② premium Key 直连 mimo-v2.5（opencode 已配置、不在规则） ===")
    code, body, served = post_chat("mimo-v2.5", PREMIUM_KEY)
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    ok = code == 200 and "opencode" in served
    results.append(ok)
    print(f"  HTTP {code} X-Served-By={served} content={str(content)[:30]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:200]}")

    print("=== ③ premium Key 直连 kimi-for-coding（kimi code 源） ===")
    code, body, served = post_chat("kimi-for-coding", PREMIUM_KEY)
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    ok = code == 200 and "kimi" in served
    results.append(ok)
    print(f"  HTTP {code} X-Served-By={served} content={str(content)[:30]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:200]}")

    print("=== ④ free Key 直连 mimo-v2.5 → 应 403（premium 组拦截） ===")
    code, body, _ = post_chat("mimo-v2.5", FREE_KEY)
    ok = code == 403
    results.append(ok)
    print(f"  HTTP {code} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:200]}")

    print()
    passed = sum(1 for r in results if r)
    print(f"=== {passed}/{len(results)} 通过 ===")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

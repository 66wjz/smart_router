"""生产真实链路验证：3 入站协议 × 出站协议分发（不用 mock，打真实上游）

用例：
 1. openai 入站 → openai 出站（newapi 规则内模型直连）
 2. anthropic 入站 → openai 出站（x-api-key + anthropic 格式调 newapi 模型）
 3. responses 入站 → openai 出站（Codex 风格调 newapi 模型）
 4. anthropic 入站 → anthropic 出站（临时别名指向 opencode minimax-m2.7，双向转换链）
 5. responses 入站流式 → openai 出站流式（SSE 事件序列）
"""
import json
import sys
import urllib.request

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

PROD = "http://8.137.195.192:10002"
FREE_KEY = os.environ.get("SR_FREE_KEY", "")
PREMIUM_KEY = os.environ.get("SR_PREMIUM_KEY", "")


def post(path: str, body: dict, key: str, x_api_key: bool = False, timeout: int = 120) -> tuple[int, dict, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(PROD + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if x_api_key:
        req.add_header("x-api-key", key)
        req.add_header("anthropic-version", "2023-06-01")
    else:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, dict(e.headers), {}


def prod_ssh(cmd: str) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    _, o, e = client.exec_command(cmd, timeout=60)
    out = (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()
    client.close()
    return out


def main() -> int:
    results = []

    print("=== 用例1：openai 入站 → openai 出站（newapi minimax-m3 直连） ===")
    code, hdrs, body = post("/v1/chat/completions", {
        "model": "minimaxai/minimax-m3",
        "messages": [{"role": "user", "content": "回复一个字：好"}],
        "max_tokens": 32,
    }, FREE_KEY)
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    served = hdrs.get("X-Served-By") or hdrs.get("x-served-by", "")
    ok = code == 200 and content
    results.append(ok)
    print(f"  HTTP {code} X-Served-By={served} content={str(content)[:40]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:300]}")

    print("=== 用例2：anthropic 入站 → openai 出站（x-api-key） ===")
    code, hdrs, body = post("/v1/messages", {
        "model": "minimaxai/minimax-m3",
        "max_tokens": 32,
        "system": "你是简洁助手",
        "messages": [{"role": "user", "content": "回复一个字：好"}],
    }, FREE_KEY, x_api_key=True)
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    ok = code == 200 and body.get("type") == "message" and body.get("role") == "assistant" and text and body.get("stop_reason")
    results.append(ok)
    print(f"  HTTP {code} type={body.get('type')} stop_reason={body.get('stop_reason')} text={text[:40]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:300]}")

    print("=== 用例3：responses 入站 → openai 出站（Codex 风格） ===")
    code, hdrs, body = post("/v1/responses", {
        "model": "minimaxai/minimax-m3",
        "instructions": "你是简洁助手",
        "input": "回复一个字：好",
        "max_output_tokens": 32,
    }, FREE_KEY)
    text = ""
    for item in body.get("output", []):
        if item.get("type") == "message":
            text = "".join(c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text")
    ok = code == 200 and body.get("object") == "response" and body.get("status") == "completed" and text
    results.append(ok)
    print(f"  HTTP {code} object={body.get('object')} status={body.get('status')} text={text[:40]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:300]}")

    print("=== 用例4：anthropic 入站 → anthropic 出站（opencode minimax-m2.7，临时别名） ===")
    login = prod_ssh("curl -s -X POST http://127.0.0.1:10002/admin/api/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"smart-router-2026\"}'")
    token = json.loads(login).get("token", "") if login.startswith("{") else ""
    if not token:
        results.append(None)
        print("  [SKIP] 生产管理员登录失败，跳过")
    else:
        prod_ssh(f"curl -s -X POST http://127.0.0.1:10002/admin/api/model-pointers -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' -d '{{\"name\":\"t-mmx\",\"target_model\":\"minimax-m2.7\",\"upstream\":\"opencode go\"}}' >/dev/null")
        prod_ssh(f"curl -s -X POST http://127.0.0.1:10002/admin/api/reload -H 'Authorization: Bearer {token}' >/dev/null")
        try:
            code, hdrs, body = post("/v1/messages", {
                "model": "t-mmx",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "回复一个字：好"}],
            }, PREMIUM_KEY, x_api_key=True, timeout=180)
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
            served = hdrs.get("X-Served-By") or hdrs.get("x-served-by", "")
            ok = code == 200 and text
            results.append(ok)
            print(f"  HTTP {code} X-Served-By={served} text={text[:40]!r} -> {'PASS' if ok else 'FAIL: ' + json.dumps(body, ensure_ascii=False)[:300]}")
        finally:
            prod_ssh(f"curl -s -X DELETE 'http://127.0.0.1:10002/admin/api/model-pointers/t-mmx' -H 'Authorization: Bearer {token}' >/dev/null")
            prod_ssh(f"curl -s -X POST http://127.0.0.1:10002/admin/api/reload -H 'Authorization: Bearer {token}' >/dev/null")
            print("  临时别名已清理")

    print("=== 用例5：responses 入站流式 → openai 出站流式 ===")
    data = json.dumps({"model": "minimaxai/minimax-m3", "input": "回复一个字：好", "stream": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(PROD + "/v1/responses", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {FREE_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        need = ["response.created", "response.output_text.delta", "response.completed"]
        missing = [n for n in need if f"event: {n}" not in raw]
        has_text = '"delta"' in raw
        ok = not missing and has_text
        results.append(ok)
        print(f"  事件: {'PASS 全在' if not missing else 'FAIL 缺 ' + ','.join(missing)}；delta 文本: {'有' if has_text else '无'}")
    except Exception as e:
        results.append(False)
        print(f"  FAIL: {e}")

    print()
    passed = sum(1 for r in results if r is True)
    skipped = sum(1 for r in results if r is None)
    print(f"=== 总计 {passed}/{len(results) - skipped} 通过（跳过 {skipped}） ===")
    return 0 if all(r in (True, None) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

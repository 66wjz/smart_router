"""生产诊断：opencode 403 根因 + 延迟分层测量

1. 从生产 DB 读 opencode 上游配置（base_url + 首 Key）
2. 服务器本机直连 opencode：gpt-5.6-luna 走 /v1/responses 看原始 403 响应体
3. 同 Key 直连 deepseek-v4-flash 走 /v1/chat/completions（对照组）
4. 延迟分解：curl -w 打 DNS/TCP/TLS/首字节/总耗时
"""
import json

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)


def run(cmd: str, timeout=90) -> str:
    _, o, e = client.exec_command(cmd, timeout=timeout)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


up = run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
         "import sqlite3, json; con = sqlite3.connect('smart_router.db'); "
         "rows = con.execute(\\\"SELECT upstream_id, base_url FROM up_upstream WHERE base_url LIKE '%opencode%'\\\").fetchall(); "
         "print(json.dumps(rows))\"")
print(f"=== opencode 上游 ===\n{up}")

rows = json.loads(up) if up.startswith("[") else []
if not rows:
    print("!! 生产库未找到 opencode 上游，请确认上游 ID 或 base_url")
    raise SystemExit(1)
uid, base_url = rows[0]

key = run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          f"r = con.execute(\\\"SELECT api_key FROM up_upstream_key WHERE upstream_id='{uid}' AND enabled=1 LIMIT 1\\\").fetchone(); "
          "print(r[0] if r else '')\"")
if not key:
    key = run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
              "import sqlite3; con = sqlite3.connect('smart_router.db'); "
              f"r = con.execute(\\\"SELECT api_key FROM up_upstream WHERE upstream_id='{uid}'\\\").fetchone(); "
              "print(r[0] if r else '')\"")
print(f"上游 {uid}，base_url={base_url}，Key={'已获取' if key else '未获取'}")

TIMING = '-w "\\nDNS:%{time_namelookup} TCP:%{time_connect} TLS:%{time_appconnect} 首字节:%{time_starttransfer} 总:%{time_total}s\\n"'

print("\n=== ① 直连 gpt-5.6-luna（/v1/responses，原始响应 + 计时）===")
print(run(f"curl -s {TIMING} -X POST '{base_url}/v1/responses' "
          f"-H 'Authorization: Bearer {key}' -H 'Content-Type: application/json' "
          "-d '{\"model\":\"gpt-5.6-luna\",\"input\":\"hi\",\"max_output_tokens\":16}' | head -c 800", timeout=120))

print("\n=== ② 直连 deepseek-v4-flash（/v1/chat/completions 对照组 + 计时）===")
print(run(f"curl -s {TIMING} -X POST '{base_url}/v1/chat/completions' "
          f"-H 'Authorization: Bearer {key}' -H 'Content-Type': application/json' "
          "-d '{\"model\":\"deepseek-v4-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":16}' | head -c 800", timeout=120))
# 上一行 header 引号容错：重跑一次规范版
print(run(f"curl -s {TIMING} -X POST '{base_url}/v1/chat/completions' "
          f"-H 'Authorization: Bearer {key}' -H 'Content-Type: application/json' "
          "-d '{\"model\":\"deepseek-v4-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":16}' | head -c 800", timeout=120))

client.close()

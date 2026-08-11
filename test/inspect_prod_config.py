"""只读检查生产配置：客户端 Key、上游源与模型协议标注（为真实链路测试选料）"""
import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)


def run(cmd: str) -> str:
    _, o, e = client.exec_command(cmd, timeout=30)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("=== 客户端 Key（脱敏） ===")
print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          "[print(r[0], r[1][:12]+'...', r[2], 'enabled' if r[3] else 'disabled') for r in con.execute('SELECT name, key_value, groups, enabled FROM api_api_key')]\""))
print()
print("=== 上游源与模型协议 ===")
print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          "[print(r[0], '|', r[1], '| fmt:', r[2], '| grp:', r[3], '| enabled:', r[4], '| sr:', r[5], '| models:', (r[6] or '')[:300]) "
          "for r in con.execute('SELECT upstream_id, base_url, format, group_name, enabled, smart_retry, models FROM up_upstream')]\""))
print()
print("=== 别名 ===")
print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          "[print(r) for r in con.execute('SELECT name, target_model, upstream_id FROM pt_pointer')]\""))
client.close()

"""只读检查生产路由规则候选（确认哪些模型可被客户端直接路由）"""
import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)


def run(cmd: str) -> str:
    _, o, e = client.exec_command(cmd, timeout=30)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          "[print(r) for r in con.execute('SELECT r.name, c.model, c.upstream_id, c.priority, c.weight FROM rule_candidate c JOIN rule_rule r ON r.id=c.rule_id ORDER BY r.sort_order, c.priority')]\""
          ))
print()
print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
          "import sqlite3; con = sqlite3.connect('smart_router.db'); "
          "print('default_upstream:', con.execute(\\\"SELECT value FROM sys_setting WHERE key='default_upstream'\\\").fetchone())\""))
client.close()

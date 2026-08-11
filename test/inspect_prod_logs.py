"""查看生产 smart-router 最近日志，定位"添加上游源报错"根因"""
import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)


def run(cmd: str) -> str:
    _, o, e = client.exec_command(cmd, timeout=30)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("=== 含错误关键词的最近日志 ===")
print(run("journalctl -u smart-router -n 200 --no-pager | grep -iE 'error|exception|traceback|operational|422' | tail -30"))
print()
print("=== 最近 12 行原始日志 ===")
print(run("journalctl -u smart-router -n 12 --no-pager"))
print()
print("=== 生产 DB up_upstream 表结构 ===")
print(run("cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \"import sqlite3; print([r[1] for r in sqlite3.connect('smart_router.db').execute('PRAGMA table_info(up_upstream)')])\""))
client.close()

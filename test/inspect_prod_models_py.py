"""只读对比：生产 models.py 内容 vs 本地版本（定位 /v1/models 未按配置过滤的根因）"""
import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)


def run(cmd: str) -> str:
    _, o, e = client.exec_command(cmd, timeout=30)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("=== 生产 models.py 关键行（含过滤逻辑 vs 代理拉取） ===")
print(run("cat /opt/smart-router/backend/app/api/v1/models.py"))
print()
print("=== 生产 models.py 大小/修改时间 ===")
print(run("ls -l /opt/smart-router/backend/app/api/v1/models.py"))
client.close()

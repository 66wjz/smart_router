"""部署 step1：备份 v4 + 创建 conda python3.12 环境"""
import sys

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")


def run(client, cmd, timeout=600) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return f"{out}\n{err}".strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)

    print("[1] 备份 v4 目录")
    print(run(client, "if [ -d /opt/smart-router ] && [ ! -d /opt/smart-router.v4.bak ]; then mv /opt/smart-router /opt/smart-router.v4.bak && echo '已备份为 /opt/smart-router.v4.bak'; else echo '无 v4 或已备份'; fi"))

    print("\n[2] 检查 conda env")
    envs = run(client, "/root/miniconda3/bin/conda env list | grep smart-router || echo NOT_EXIST")
    if "NOT_EXIST" in envs:
        print("[3] 创建 conda 环境 python3.12（可能耗时 1-2 分钟）")
        print(run(client, "/root/miniconda3/bin/conda create -n smart-router python=3.12 -y", timeout=900))
    else:
        print("[3] 环境已存在，跳过创建")

    print("\n[4] 确认 python 版本")
    print(run(client, "/root/miniconda3/envs/smart-router/bin/python --version"))
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

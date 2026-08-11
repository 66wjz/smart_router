"""用清华镜像创建 conda 3.12 环境并安装后端依赖"""
import sys

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")


def run(client, cmd, timeout=900) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return (out + "\n" + err).strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)

    print("[1] 配置清华镜像")
    print(run(client, "/root/miniconda3/bin/conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main", 60))
    print(run(client, "/root/miniconda3/bin/conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free", 60))
    print(run(client, "/root/miniconda3/bin/conda config --set show_channel_urls yes", 60))

    print("[2] 创建环境（清华源，可能 1-3 分钟）")
    print(run(client, "/root/miniconda3/bin/conda create -n smart-router python=3.12 -y", 900))

    print("[3] 确认 python")
    print(run(client, "/root/miniconda3/envs/smart-router/bin/python --version", 30))

    print("[4] 安装后端依赖（pip 清华源）")
    pip = "/root/miniconda3/envs/smart-router/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple"
    print(run(client, f"{pip} fastapi uvicorn[standard] httpx pyyaml", 600))

    print("[5] 确认依赖")
    print(run(client, "/root/miniconda3/envs/smart-router/bin/python -c \"import fastapi,uvicorn,httpx,yaml; print('deps ok', fastapi.__version__)\"", 30))
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

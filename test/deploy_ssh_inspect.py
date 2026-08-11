"""勘察服务器现有 smart-router 部署与可用运行环境"""
import sys

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)

    cmds = [
        "echo '=== /opt/smart-router 内容 ==='; ls -la /opt/smart-router/ | head -30",
        "echo '=== /opt/smart-router 文件树(2层) ==='; find /opt/smart-router -maxdepth 2 -type f | head -40",
        "echo '=== 运行进程 ==='; ps aux | grep -E 'python|uvicorn|gunicorn' | grep -v grep | head -10",
        "echo '=== conda 环境 ==='; ls /root/miniconda3/envs/ 2>/dev/null; /root/miniconda3/bin/python --version 2>&1",
        "echo '=== miniconda python ==='; /root/miniconda3/bin/conda --version 2>&1 | head -1",
        "echo '=== nginx 配置 ==='; cat /etc/nginx/nginx.conf 2>/dev/null | grep -A5 'server {' | head -20; ls /etc/nginx/conf.d/ /etc/nginx/sites-enabled/ 2>/dev/null",
        "echo '=== 80端口进程 ==='; ss -tlnp | grep ':80 ' ",
        "echo '=== systemd 服务 ==='; systemctl list-units --type=service 2>/dev/null | grep -iE 'smart|router|nginx|uvicorn' | head",
        "echo '=== 磁盘与swap ==='; free -h; df -h / | tail -1; swapon --show 2>/dev/null | head -3",
        "echo '=== 防火墙 ==='; firewall-cmd --state 2>&1 | head -1; systemctl status firewalld 2>/dev/null | head -3",
        "echo '=== pip ==='; /root/miniconda3/bin/pip --version 2>&1 | head -1",
    ]
    for cmd in cmds:
        _, stdout, stderr = client.exec_command(cmd, timeout=15)
        out = stdout.read().decode("utf-8", "ignore").strip()
        err = stderr.read().decode("utf-8", "ignore").strip()
        print(f"{out or err or '(空)'}\n---")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""SSH 连接测试：8.137.195.192 部署前环境勘察"""
import sys

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")


def main() -> int:
    host = "8.137.195.192"
    port = 22
    user = "root"
    pwd = SSH_PASS

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=pwd, timeout=15, banner_timeout=15)
    except Exception as e:
        print(f"[FAIL] SSH 连接失败: {e}")
        return 1
    print(f"[PASS] SSH 连接成功: {user}@{host}:{port}")

    cmds = [
        "hostname && uname -a",
        "cat /etc/os-release | head -3",
        "python3 --version; python --version 2>&1 | head -1",
        "uv --version 2>&1 | head -1",
        "node --version 2>&1 | head -1; npm --version 2>&1 | head -1",
        "docker --version 2>&1 | head -1",
        "systemctl is-active nginx 2>/dev/null; ls /etc/nginx/conf.d/ 2>/dev/null | head -5",
        "free -h | head -2; df -h / | tail -1",
        "ss -tlnp | grep -E ':(10002|80|443|5173)' || echo '端口 10002/80 未监听'",
        "ls /root/ 2>/dev/null | head -20",
        "ls /opt/ 2>/dev/null | head -20",
    ]
    for cmd in cmds:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
        out = stdout.read().decode("utf-8", "ignore").strip()
        err = stderr.read().decode("utf-8", "ignore").strip()
        print(f"\n$ {cmd}\n  {out or err or '(空)'}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

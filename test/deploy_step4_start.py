"""部署 step4：清理服务器 db 杂文件 + 上传干净 db + systemd 服务 + 启动验证"""
import sys
import time

import os

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

LOCAL_DB = r"E:\80-project_dev\04_smart-router(starting)\backend\smart_router.db"
UNIT = """[Unit]
Description=Smart Router v5
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/smart-router/backend
Environment=FRONTEND_DIST=/opt/smart-router/frontend_dist
ExecStart=/root/miniconda3/bin/python run.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return (stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")).strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 清理服务器 db 杂文件")
    print(run(client, "rm -f /opt/smart-router/backend/smart_router.db-shm /opt/smart-router/backend/smart_router.db-wal /opt/smart-router/backend/app/smart_router.db* && echo cleaned"))

    print("[2] 上传干净数据库")
    sftp.put(LOCAL_DB, "/opt/smart-router/backend/smart_router.db")
    print(f"  上传 {__import__('os').path.getsize(LOCAL_DB)}B")

    print("[3] 写 systemd 服务")
    sftp.open("/etc/systemd/system/smart-router.service", "w").write(UNIT)
    print("  unit written")
    print(run(client, "systemctl daemon-reload && systemctl enable smart-router 2>&1 | tail -1"))

    print("[4] 启动服务")
    print(run(client, "systemctl restart smart-router && sleep 6 && systemctl is-active smart-router"))
    print(run(client, "ss -tlnp | grep 10002 || echo '10002 未监听'"))

    print("[5] 本地验证")
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    print(run(client, "curl -s -X POST http://127.0.0.1:10002/admin/api/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"smart-router-2026\"}' | head -c 80"))
    print(run(client, "curl -s http://127.0.0.1:10002/v1/status | head -c 120"))

    print("[6] 服务日志尾部")
    print(run(client, "journalctl -u smart-router -n 8 --no-pager | tail -8"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

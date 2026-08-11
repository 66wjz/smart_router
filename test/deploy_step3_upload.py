"""部署 step3：SFTP 上传 backend 代码 + 前端 dist 到服务器"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
LOCAL_DIST = r"E:\80-project_dev\04_smart-router(starting)\frontend\dist"
REMOTE_BACKEND = "/opt/smart-router/backend"
REMOTE_DIST = "/opt/smart-router/frontend_dist"
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules", "frontend_dist"}
EXCLUDE_EXTS = {".pyc", ".pyo"}


def upload_dir(sftp, local, remote):
    for root, dirs, files in os.walk(local):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(root, local)
        target = remote if rel == "." else f"{remote}/{rel.replace(os.sep, '/')}"
        try:
            sftp.stat(target)
        except FileNotFoundError:
            sftp.mkdir(target)
            print(f"  mkdir {target}")
        for f in files:
            if os.path.splitext(f)[1] in EXCLUDE_EXTS:
                continue
            src = os.path.join(root, f)
            dst = f"{target}/{f}"
            sftp.put(src, dst)
            print(f"  up {dst} ({os.path.getsize(src)}B)")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 清理旧目录")
    _, o, _ = client.exec_command("rm -rf /opt/smart-router/backend /opt/smart-router/frontend_dist && mkdir -p /opt/smart-router/backend /opt/smart-router/frontend_dist", timeout=30)
    o.read()

    print("[2] 上传 backend 代码")
    upload_dir(sftp, LOCAL_BACKEND, REMOTE_BACKEND)

    print("[3] 上传 frontend_dist")
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)

    print("[4] 校验关键文件")
    _, o, _ = client.exec_command("ls /opt/smart-router/backend/ /opt/smart-router/frontend_dist/ | head -30; echo ---; ls -la /opt/smart-router/backend/smart_router.db", timeout=30)
    print(o.read().decode("utf-8", "ignore"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

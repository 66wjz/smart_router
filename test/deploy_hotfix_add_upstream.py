"""热修部署：添加上游源 500 修复（upstream_repo.py）+ 接入说明 UI 调整（dist）"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
LOCAL_DIST = r"E:\80-project_dev\04_smart-router(starting)\frontend\dist"
REMOTE_BACKEND = "/opt/smart-router/backend"
REMOTE_DIST = "/opt/smart-router/frontend_dist"


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return (stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")).strip()


def upload_dir(sftp, local, remote):
    for root, dirs, files in os.walk(local):
        rel = os.path.relpath(root, local)
        target = remote if rel == "." else f"{remote}/{rel.replace(os.sep, '/')}"
        try:
            sftp.stat(target)
        except FileNotFoundError:
            sftp.mkdir(target)
        for f in files:
            sftp.put(os.path.join(root, f), f"{target}/{f}")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传 upstream_repo.py（api_key None→空串修复）")
    sftp.put(os.path.join(LOCAL_BACKEND, r"app\repositories\upstream_repo.py"),
             f"{REMOTE_BACKEND}/app/repositories/upstream_repo.py")
    print("  up done")

    print("[2] 替换前端 dist（接入说明复制按钮右移）")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)
    print(f"  dist 文件数: {run(client, f'find {REMOTE_DIST} -type f | wc -l')}")

    print("[3] 语法预检")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile app/repositories/upstream_repo.py && echo COMPILE_OK"))

    print("[4] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CH-010 增量部署：responses 入站（3 个后端文件，无前端/DB 变更），重启并验证"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
    r"app\upstream\responses_adapter.py",
    r"app\api\v1\responses.py",
    r"app\api\v1\router.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
REMOTE_BACKEND = "/opt/smart-router/backend"


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return (stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")).strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传 3 个后端文件（含新增 api/v1/responses.py）")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 语法预检")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/upstream/responses_adapter.py app/api/v1/responses.py app/api/v1/router.py && echo COMPILE_OK"))

    print("[3] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    print("[4] 入站路由存在性（无 Key 应 401 而非 404）")
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/responses -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/responses -H 'Content-Type: application/json' -d '{}'"))
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/messages  -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/messages -H 'Content-Type: application/json' -d '{}'"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""纯前端增量部署：只替换 frontend_dist（静态文件由后端直接读取，无需重启）"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

LOCAL_DIST = r"E:\80-project_dev\04_smart-router(starting)\frontend\dist"
REMOTE_DIST = "/opt/smart-router/frontend_dist"


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return (stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")).strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 替换前端 dist")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    count = 0
    for root, dirs, files in os.walk(LOCAL_DIST):
        rel = os.path.relpath(root, LOCAL_DIST)
        target = REMOTE_DIST if rel == "." else f"{REMOTE_DIST}/{rel.replace(os.sep, '/')}"
        try:
            sftp.stat(target)
        except FileNotFoundError:
            sftp.mkdir(target)
        for f in files:
            sftp.put(os.path.join(root, f), f"{target}/{f}")
            count += 1
    print(f"  上传 {count} 个文件")

    print("[2] 验证（页面可访问 + 静态资源 200）")
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    print(run(client, f"ls {REMOTE_DIST}/assets | head -3"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

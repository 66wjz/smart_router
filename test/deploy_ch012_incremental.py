"""CH-012/CH-013 增量部署：变更后端文件 + 前端 dist + up_upstream 加 smart_retry 列，重启并验证

不触碰生产业务数据（只加列；frontend_dist 整体替换不影响 DB）。
"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
    r"app\repositories\upstream_repo.py",
    r"app\core\config.py",
    r"app\services\config_service.py",
    r"app\api\admin\config.py",
    r"app\schemas\upstream.py",
    r"app\upstream\openai_adapter.py",
    r"app\upstream\anthropic_adapter.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
LOCAL_DIST = r"E:\80-project_dev\04_smart-router(starting)\frontend\dist"
REMOTE_BACKEND = "/opt/smart-router/backend"
REMOTE_DIST = "/opt/smart-router/frontend_dist"

ALTER_SQL = (
    "import sqlite3; con = sqlite3.connect('smart_router.db'); "
    "cols = [r[1] for r in con.execute('PRAGMA table_info(up_upstream)')]; "
    "con.execute('ALTER TABLE up_upstream ADD COLUMN smart_retry INTEGER NOT NULL DEFAULT 0') "
    "if 'smart_retry' not in cols else None; "
    "con.commit(); print('smart_retry' in [r[1] for r in con.execute('PRAGMA table_info(up_upstream)')]); "
    "con.close()"
)


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

    print("[1] 上传 7 个后端变更文件")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 生产 DB 加 smart_retry 列（幂等）")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -c \"{ALTER_SQL}\""))

    print("[3] 替换前端 dist")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)
    print(f"  dist 文件数: {run(client, f'find {REMOTE_DIST} -type f | wc -l')}")

    print("[4] 语法预检（服务器侧 py_compile）")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/repositories/upstream_repo.py app/core/config.py app/services/config_service.py "
                      "app/api/admin/config.py app/schemas/upstream.py app/upstream/openai_adapter.py "
                      "app/upstream/anthropic_adapter.py && echo COMPILE_OK"))

    print("[5] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "ss -tlnp | grep 10002 || echo '10002 未监听'"))

    print("[6] 生产验证")
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    print(run(client, "journalctl -u smart-router -n 5 --no-pager | tail -5"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

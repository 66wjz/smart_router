"""CH-019 增量部署（Ubuntu 10.10.0.2）：同名聚合+模型管理+用量统计
后端 16 文件 + 新文件 4 个 + 增量 SQL 06 + 前端 dist，重启并验证
用法：$env:SR_SSH_PASS='...' 后 python test/deploy_ch019_incremental.py"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")
SSH_HOST = "10.10.0.2"

BACKEND_FILES = [
    r"app\core\health.py",
    r"app\core\probe.py",
    r"app\core\config.py",
    r"app\core\router_engine.py",
    r"app\core\usage.py",
    r"app\services\router_service.py",
    r"app\services\dashboard_service.py",
    r"app\repositories\upstream_repo.py",
    r"app\repositories\usage_repo.py",
    r"app\api\admin\upstreams.py",
    r"app\api\admin\usage.py",
    r"app\api\admin\router.py",
    r"app\api\v1\chat.py",
    r"app\api\v1\messages.py",
    r"app\api\v1\responses.py",
    r"app\api\v1\models.py",
    r"app\api\v1\status.py",
    r"app\schemas\upstream.py",
    r"app\main.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router\backend"
LOCAL_SQL = r"E:\80-project_dev\04_smart-router\sql\06_用量统计与自动聚合.sql"
LOCAL_DIST = r"E:\80-project_dev\04_smart-router\frontend\dist"
REMOTE_BACKEND = "/opt/smart-router/backend"
REMOTE_SQL = "/opt/smart-router/sql/06_用量统计与自动聚合.sql"
REMOTE_DIST = "/opt/smart-router/frontend_dist"


def run(client, cmd, timeout=120) -> str:
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
    if not SSH_PASS:
        print("!! 请先设置 $env:SR_SSH_PASS")
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传后端文件")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 上传增量 SQL 并迁移生产 DB（幂等）")
    sftp.put(LOCAL_SQL, REMOTE_SQL)
    print(f"  up {REMOTE_SQL}")
    migrate = (
        f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python - <<'EOF'\n"
        "import sqlite3\n"
        f"con = sqlite3.connect('smart_router.db')\n"
        f"raw = open('{REMOTE_SQL}', encoding='utf-8').read()\n"
        "import re\n"
        "lines = [l for l in raw.splitlines() if not l.strip().startswith('--')]\n"
        "stmts = [s.strip() for s in '\\n'.join(lines).split(';') if s.strip()]\n"
        "for st in stmts:\n"
        "    try:\n"
        "        con.execute(st); print('OK:', st[:60])\n"
        "    except Exception as e:\n"
        "        print('SKIP:', st[:40], '->', e)\n"
        "con.commit()\n"
        "print('tables:', [r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='log_usage'\")])\n"
        "EOF"
    )
    print(run(client, migrate, timeout=90))

    print("[3] 语法预检")
    files_str = " ".join(f.replace(os.sep, "/") for f in BACKEND_FILES)
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile {files_str} && echo COMPILE_OK"))

    print("[4] 替换前端 dist")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)
    print(f"  dist 文件数: {run(client, f'find {REMOTE_DIST} -type f | wc -l')}")

    print("[5] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    print(run(client, "curl -s http://127.0.0.1:10002/health"))

    print("[6] 冒烟：新端点存活")
    print(run(client, "curl -s -o /dev/null -w 'GET /admin/api/usage/summary -> %{http_code}\\n' 'http://127.0.0.1:10002/admin/api/usage/summary?range=today'"))
    print(run(client, "curl -s -o /dev/null -w 'PATCH /admin/api/upstreams/x/models -> %{http_code}\\n' -X PATCH 'http://127.0.0.1:10002/admin/api/upstreams/x/models?model=y' -H 'Content-Type: application/json' -d '{\"enabled\": false}'"))
    print(run(client, "curl -s -o /dev/null -w 'GET /v1/status -> %{http_code}\\n' http://127.0.0.1:10002/status"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

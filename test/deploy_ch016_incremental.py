"""CH-016 增量部署：上游源多分组（8 后端文件 + 增量 SQL 05 迁移生产 DB + dist）"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
    r"app\repositories\upstream_repo.py",
    r"app\core\config.py",
    r"app\core\router_engine.py",
    r"app\services\router_service.py",
    r"app\services\config_service.py",
    r"app\api\v1\models.py",
    r"app\api\admin\groups.py",
    r"app\schemas\upstream.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
LOCAL_SQL = r"E:\80-project_dev\04_smart-router(starting)\sql\increment\05_增量_20260811_上游多分组.sql"
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
    if not SSH_PASS:
        print("!! 请先设置 $env:SR_SSH_PASS")
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传 8 个后端文件 + 增量 SQL")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")
    sftp.put(LOCAL_SQL, "/tmp/inc05.sql")
    print("  up /tmp/inc05.sql")

    print("[2] 生产 DB 迁移（幂等）")
    migrate = (
        "cd /opt/smart-router/backend && /root/miniconda3/bin/python -c \""
        "import sqlite3; con = sqlite3.connect('smart_router.db'); "
        "raw = open('/tmp/inc05.sql', encoding='utf-8').read(); "
        "lines = [l for l in raw.splitlines() if not l.strip().startswith('--')]; "
        "stmts = [s.strip() for s in '\\n'.join(lines).split(';') if s.strip()]; "
        "[(lambda st: (con.execute(st), print('OK:', st[:50])))(st) if True else None for st in stmts]\" 2>&1 | head -5; "
        "echo '(duplicate column 报错可忽略)'"
    )
    # 上面 lambda 方式遇 duplicate 会中断，改用逐个 try 的脚本
    migrate = (
        "cd /opt/smart-router/backend && /root/miniconda3/bin/python - <<'EOF'\n"
        "import sqlite3\n"
        "con = sqlite3.connect('smart_router.db')\n"
        "raw = open('/tmp/inc05.sql', encoding='utf-8').read()\n"
        "lines = [l for l in raw.splitlines() if not l.strip().startswith('--')]\n"
        "stmts = [s.strip() for s in '\\n'.join(lines).split(';') if s.strip()]\n"
        "for st in stmts:\n"
        "    try:\n"
        "        con.execute(st); print('OK:', st[:50])\n"
        "    except Exception as e:\n"
        "        print('SKIP:', st[:40], '->', e)\n"
        "con.commit()\n"
        "print([r for r in con.execute('SELECT upstream_id, groups FROM up_upstream')])\n"
        "EOF"
    )
    print(run(client, migrate, timeout=90))

    print("[3] 语法预检")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/repositories/upstream_repo.py app/core/config.py app/core/router_engine.py "
                      "app/services/router_service.py app/services/config_service.py "
                      "app/api/v1/models.py app/api/admin/groups.py app/schemas/upstream.py && echo COMPILE_OK"))

    print("[4] 替换前端 dist")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)
    print(f"  dist 文件数: {run(client, f'find {REMOTE_DIST} -type f | wc -l')}")

    print("[5] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

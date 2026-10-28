"""CH-052 部署：会话亲和（缓存优先路由）v5.4.0

用法：
    $env:SR_SSH_PASS='<SSH密码>'
    python test/deploy_ch052.py

本轮改动：
- 新文件 backend/app/core/affinity.py
- 后端 11 个文件（含 config_aggregation 轻量访问器）
- 新增前端 dist（编辑弹窗亲和三选 + 卡片徽标）
- 增量 SQL 13（agg_unified.affinity + log_usage 三列）；重启前必须迁移

步骤：预检 → 备份（DB 在线备份 + 代码 + dist）→ 传 SQL → 预迁移 → 校验列 →
      传后端 → 换 dist → 清 pycache/chown → compileall → 重启 → 冒烟 → 日志
每步失败即中止；中止点尽量落在替换代码之前。
"""

import io
import os
import sys
import tarfile
import time

import paramiko

HOST = "10.10.0.2"
USER = "root"
SSH_PASS = os.environ.get("SR_SSH_PASS", "")
REMOTE_ROOT = "/opt/smart-router"
REMOTE_BACKEND = f"{REMOTE_ROOT}/backend"
REMOTE_SQL = f"{REMOTE_ROOT}/sql"
REMOTE_DIST = f"{REMOTE_ROOT}/frontend_dist"
REMOTE_DB = f"{REMOTE_BACKEND}/smart_router.db"
REMOTE_PY = f"{REMOTE_BACKEND}/.venv/bin/python"
OWNER = "wjz666123"

LOCAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_FILES = [
    "backend/app/core/affinity.py",
    "backend/app/core/config.py",
    "backend/app/core/config_aggregation.py",
    "backend/app/core/key_pool.py",
    "backend/app/services/router_service.py",
    "backend/app/services/config_service.py",
    "backend/app/repositories/usage_repo.py",
    "backend/app/repositories/aggregation_repo.py",
    "backend/app/api/admin/aggregations.py",
    "backend/app/main.py",
    "backend/run.py",
    "backend/pyproject.toml",
]

SQL_FILE = "sql/increment/13_增量_20261028_会话亲和.sql"

MIGRATE_HELPER = '''import sqlite3, sys
db, path = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
con.execute("PRAGMA busy_timeout=15000")
raw = open(path, encoding="utf-8").read()
sql = "\\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
stmts = [s.strip() for s in sql.split(";") if s.strip()]
ok = skip = 0
for st in stmts:
    try:
        con.execute(st)
        ok += 1
    except Exception as e:
        if "duplicate column" in str(e).lower():
            skip += 1
        else:
            print("FAIL:", " ".join(st.split())[:80], "->", e)
            con.close()
            sys.exit(1)
con.commit()
print("APPLIED ok=%d skip=%d <- %s" % (ok, skip, path.rsplit("/", 1)[-1]))
'''

SMOKE = '''import json, sqlite3, urllib.request

BASE = "http://127.0.0.1:10002"
DB = "/opt/smart-router/backend/smart_router.db"


def http(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as e:
        return 0, {"error": str(e)}


con = sqlite3.connect(DB)
agg_cols = [r[1] for r in con.execute("PRAGMA table_info(agg_unified)")]
log_cols = [r[1] for r in con.execute("PRAGMA table_info(log_usage)")]
print("SCHEMA agg.affinity:", "affinity" in agg_cols)
print("SCHEMA log:", [c for c in ("affinity_key", "affinity_hit", "switch_reason") if c in log_cols])
print("AGG total:", con.execute("SELECT COUNT(*) FROM agg_unified").fetchone()[0],
      "| affinity off:", con.execute("SELECT COUNT(*) FROM agg_unified WHERE affinity = 0").fetchone()[0],
      "| affinity on:", con.execute("SELECT COUNT(*) FROM agg_unified WHERE affinity = 1").fetchone()[0])
con.close()

from app.core.config import config
from app.services.auth_service import make_admin_token

print("AFFINITY global enabled:", config.affinity_enabled,
      "ttl:", config.affinity_ttl_seconds,
      "min_prompt_tokens:", config.affinity_min_prompt_tokens,
      "max_entries:", config.affinity_max_entries)

token = make_admin_token(config.admin_config)
st, aggs = http("GET", "/admin/api/aggregations", token=token)
items = aggs.get("aggregations", []) if isinstance(aggs, dict) else []
print("AGG API:", st, "count:", len(items),
      "| has affinity field:", all("affinity" in a for a in items),
      "| explicit:", [(a["name"], a.get("affinity")) for a in items if a.get("affinity") is not None])

st, usage = http("GET", "/admin/api/usage/logs?range=today&page=1&size=3", token=token)
rows = usage.get("items", []) if isinstance(usage, dict) else []
print("USAGE API:", st, "rows:", len(rows),
      "| keys:", sorted(set(k for r in rows for k in r if k.startswith("affinity") or k == "switch_reason")))
'''


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    code = stdout.channel.recv_exit_status()
    text = (out + ("\n" + err if err else "")).strip()
    print(f"$ {cmd}\n  {text[:1500]}" if text else f"$ {cmd}")
    if code != 0:
        raise SystemExit(f"命令失败（exit={code}）：{cmd}")
    return text


def step(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    if not SSH_PASS:
        print("缺少 SR_SSH_PASS")
        return 2

    dist_dir = os.path.join(LOCAL_ROOT, "frontend", "dist")
    if not os.path.isdir(dist_dir):
        print("frontend/dist 不存在，先 npm run build")
        return 2
    dist_tgz = os.path.join(LOCAL_ROOT, "backend", ".tmp_ch052_dist.tar.gz")
    with tarfile.open(dist_tgz, "w:gz") as tf:
        for name in os.listdir(dist_dir):
            tf.add(os.path.join(dist_dir, name), arcname=name)
    print(f"dist 打包完成：{os.path.getsize(dist_tgz) / 1024:.0f} KB")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, 22, USER, SSH_PASS, timeout=20)
    print(f"已连接 {USER}@{HOST}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{REMOTE_ROOT}/backup/ch052-{ts}"

    try:
        step("0 预检：磁盘 / 服务 / 当前版本")
        run(client, "df -h /opt | tail -1; systemctl is-active smart-router")
        run(client, "curl -s http://127.0.0.1:10002/openapi.json | head -c 100")

        step("1 备份（DB 在线备份 + 旧代码 + 旧前端）")
        run(client, f"mkdir -p {backup_dir}")
        db_backup = (
            "import sqlite3\n"
            f"src = sqlite3.connect('{REMOTE_DB}')\n"
            f"dst = sqlite3.connect('{backup_dir}/smart_router.db')\n"
            "src.backup(dst)\n"
            "src.close(); dst.close()\n"
            "print('DB_BACKUP_OK')\n"
        )
        out = run(client, f"{REMOTE_PY} - <<'PYEOF'\n{db_backup}\nPYEOF", timeout=1800)
        if "DB_BACKUP_OK" not in out:
            print("!! 数据库备份失败，中止（未做任何改动）")
            return 2
        run(client,
            f"cd {REMOTE_ROOT} && tar czf {backup_dir}/backend_code.tar.gz "
            "--exclude='backend/smart_router.db*' --exclude='backend/.venv' "
            "--exclude='*__pycache__*' --exclude='backend/logs' --exclude='backend/demo.db*' "
            "backend sql frontend_dist && echo CODE_BACKUP_OK")
        run(client, f"ls -lh {backup_dir}")

        step("2 上传 SQL 并预迁移（重启前完成）")
        sftp = client.open_sftp()
        sftp.put(os.path.join(LOCAL_ROOT, SQL_FILE.replace("/", os.sep)), "/tmp/ch052_affinity.sql")
        sftp.putfo(io.BytesIO(MIGRATE_HELPER.encode("utf-8")), "/tmp/sr_migrate.py")
        sftp.close()
        run(client, f"mkdir -p {REMOTE_SQL}/increment && "
                    f"mv -f /tmp/ch052_affinity.sql {REMOTE_SQL}/increment/13_增量_20261028_会话亲和.sql && "
                    f"chown -R {OWNER}:{OWNER} {REMOTE_SQL} && echo SQL_READY")
        out = run(client, f"{REMOTE_PY} /tmp/sr_migrate.py {REMOTE_DB} "
                          f"{REMOTE_SQL}/increment/13_增量_20261028_会话亲和.sql")
        if "APPLIED" not in out:
            print("!! 迁移失败，中止（未替换代码，生产仍用旧版本）")
            return 3
        run(client, (
            "cd /opt/smart-router/backend && .venv/bin/python - <<'PYEOF'\n"
            "import sqlite3\n"
            "con = sqlite3.connect('smart_router.db')\n"
            "print('agg affinity:', [r[1] for r in con.execute('PRAGMA table_info(agg_unified)') if 'affinity' in r[1]])\n"
            "print('log cols:', [r[1] for r in con.execute('PRAGMA table_info(log_usage)') if r[1] in ('affinity_key','affinity_hit','switch_reason')])\n"
            "print('rows:', con.execute('SELECT COUNT(*) FROM log_usage').fetchone()[0])\n"
            "PYEOF"))

        step("3 上传后端代码")
        sftp = client.open_sftp()
        for rel in BACKEND_FILES:
            local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
            if not os.path.exists(local):
                raise SystemExit(f"本地文件不存在：{local}")
            tmp = f"/tmp/ch052_{os.path.basename(rel)}"
            sftp.put(local, tmp)
            run(client, f"mkdir -p {REMOTE_ROOT}/{os.path.dirname(rel)} && "
                        f"mv -f {tmp} {REMOTE_ROOT}/{rel}")
        sftp.put(dist_tgz, "/tmp/ch052_dist.tar.gz")
        sftp.close()

        step("4 替换前端 dist")
        run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && "
                    f"tar xzf /tmp/ch052_dist.tar.gz -C {REMOTE_DIST} && rm -f /tmp/ch052_dist.tar.gz && "
                    f"echo DIST_OK && ls {REMOTE_DIST} | head -5")

        step("5 清缓存 / 属主 / 编译预检")
        run(client, f"find {REMOTE_BACKEND}/app -name __pycache__ -type d -prune -exec rm -rf {{}} + ; echo PYCACHE_CLEAN")
        run(client, f"chown -R {OWNER}:{OWNER} {REMOTE_BACKEND}/app {REMOTE_BACKEND}/run.py "
                    f"{REMOTE_BACKEND}/pyproject.toml {REMOTE_DIST} && echo CHOWN_OK")
        run(client, f"cd {REMOTE_BACKEND} && {REMOTE_PY} -m compileall -q app run.py && echo COMPILE_OK")

        step("6 重启 + 冒烟")
        run(client, "systemctl restart smart-router && sleep 8 && systemctl is-active smart-router")
        run(client, "curl -s -o /dev/null -w 'GET /health -> %{http_code}\\n' http://127.0.0.1:10002/health")
        run(client, "curl -s http://127.0.0.1:10002/openapi.json | head -c 100")
        run(client, f"cd {REMOTE_BACKEND} && {REMOTE_PY} - <<'PYEOF'\n{SMOKE}\nPYEOF", timeout=120)

        step("7 前端产物含亲和开关")
        run(client, f"grep -rl '会话亲和' {REMOTE_DIST}/assets | head -3; "
                    f"ls {REMOTE_DIST}/assets | grep -c '^Aggregated-'")

        step("8 启动日志")
        run(client, "journalctl -u smart-router -n 20 --no-pager | grep -E '启动|配置已加载|ERROR|Traceback' || true")

        print(f"\n部署完成：备份 {backup_dir}")
        return 0
    finally:
        client.close()
        if os.path.exists(dist_tgz):
            os.remove(dist_tgz)


if __name__ == "__main__":
    sys.exit(main())

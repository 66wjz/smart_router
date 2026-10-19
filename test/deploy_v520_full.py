"""全量同步部署脚本：把本地 backend/ + sql/ + frontend/dist 同步到生产 10.10.0.2。

v5.2.0 首次使用（CH-020~CH-032 累计 13 项一次上线），此后作为**唯一部署工具**复用：
每次把生产对齐到本地 HEAD。迁移脚本清单 MIGRATE_FILES 需随新增量同步追加。

为什么不是增量传文件：
    CH-026 含文件拆分新增、CH-023/CH-024/CH-034/CH-036 含表结构与数据迁移。
    逐文件增量必然漏文件，改为整树同步。

两个绝对不能踩的坑（已实测确认）：
    1. **绝不执行 seed.py** —— drop_all() 会先删掉全部表再重建，生产数据全丢。
    2. **绝不「先传代码再重启」** —— 生产库缺 agg_model_group / agg_unified /
       agg_probe_config / agg_probe_template 四张表。新代码在模块导入期就会调用
       config.load()，任一 repo 抛 OperationalError 会让 load() 把上游源、规则、
       API Key 全部清空 → 网关直接不可用。
       因此本脚本在第 3 步显式跑完迁移，再在第 7 步重启。

部署顺序（关键）：
    1 备份 → 2 传 sql → 3 预迁移数据库 → 4 传后端代码 → 5 替换 dist
    → 6 清缓存 + chown → 7 语法预检 → 8 重启 + 健康检查

用法：
    $env:SR_SSH_PASS='<密码>'
    .\\backend\\.venv\\Scripts\\python.exe test\\deploy_v520_full.py --dry-run
    .\\backend\\.venv\\Scripts\\python.exe test\\deploy_v520_full.py --migrate-only
    .\\backend\\.venv\\Scripts\\python.exe test\\deploy_v520_full.py
"""

import argparse
import io
import os
import sys
import tarfile
import tempfile
import time

import paramiko

HOST = "10.10.0.2"
USER = "root"
# 密码来源优先级：
#   1) 环境变量 SR_SSH_PASS
#   2) 仓库外的本地文件（默认 E:\80-project_dev\.sr_deploy_pass）
PASS_FILE = os.environ.get("SR_SSH_PASS_FILE") or r"E:\80-project_dev\.sr_deploy_pass"


def load_pass() -> str:
    val = os.environ.get("SR_SSH_PASS", "").strip()
    if val:
        return val
    try:
        with open(PASS_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


PASS = load_pass()

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_BACKEND = os.path.join(REPO, "backend")
LOCAL_SQL = os.path.join(REPO, "sql")
LOCAL_DIST = os.path.join(REPO, "frontend", "dist")

REMOTE_ROOT = "/opt/smart-router"
REMOTE_BACKEND = f"{REMOTE_ROOT}/backend"
REMOTE_SQL = f"{REMOTE_ROOT}/sql"
REMOTE_DIST = f"{REMOTE_ROOT}/frontend_dist"
REMOTE_BACKUP = f"{REMOTE_ROOT}/backup"
REMOTE_PY = f"{REMOTE_BACKEND}/.venv/bin/python"
REMOTE_DB = f"{REMOTE_BACKEND}/smart_router.db"
SERVICE_OWNER = "wjz666123"

# 需要按序执行的迁移脚本（顺序不可调换：06 建 agg_model_group/agg_probe_config，07 才引用它们；
# 09 给 agg_unified 加 groups 列，10 依赖该列并做清理与开关翻转）
MIGRATE_FILES = (
    "sql/06_用量统计与自动聚合.sql",
    "sql/increment/06_增量_20261017_聚合探测配置.sql",
    "sql/increment/07_增量_20261017_聚合统一与探测模板.sql",
    "sql/increment/08_增量_20261017_聚合规则绑定.sql",
    "sql/increment/09_增量_20261018_聚合分组.sql",
    "sql/increment/10_增量_20261018_自动聚合开关默认关闭.sql",
)

# 远端执行迁移的助手脚本：逐条执行、容忍 duplicate column、其余错误立即报错退出
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

BACKEND_EXCLUDES = ()

# 部署后冒烟：验证 CH-034（聚合分组）与 CH-036（自动聚合开关关闭）真的生效
# 管理员账号密码从生产库读出（不硬编码、不打印），避免把凭据写进仓库
SMOKE_SCRIPT = '''import json, sqlite3, urllib.request, urllib.error

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
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


con = sqlite3.connect(DB)
row = con.execute("SELECT value FROM sys_setting WHERE key='admin'").fetchone()
cfg = json.loads(row[0]) if row else {}
user = cfg.get("username", "admin")
pwd = cfg.get("password", "")

st, body = http("POST", "/admin/api/login", {"username": user, "password": pwd})
token = json.loads(body).get("token", "") if st == 200 else ""
print("login:", st, "token:", "yes" if token else "no")

auto_off = False
st, body = http("GET", "/admin/api/config/auto-aggregate", token=token)
if st == 200:
    auto_off = json.loads(body).get("enabled") is False
print("auto-aggregate:", st, body.strip()[:60])

aggs, auto_found, has_groups = [], [], False
st, body = http("GET", "/admin/api/aggregations", token=token)
if st == 200:
    aggs = json.loads(body).get("aggregations", [])
    auto_found = [a["name"] for a in aggs if not a.get("configured", True)]
    has_groups = all("groups" in a for a in aggs)
print("aggregations:", len(aggs), [a["name"] for a in aggs])
print("auto-discovered leftovers:", auto_found)
print("groups field on all:", has_groups)
# 只有「启用的」聚合才该出现在 /v1/models（已被用户关闭的聚合本就不输出，属预期）
expected = [a["name"] for a in aggs if a.get("enabled")]
print("expected in /v1/models (启用中的聚合):", expected)

keys = con.execute("SELECT key_value FROM api_api_key WHERE enabled=1").fetchall()
key = next((k[0] for k in keys if k[0] and "CHANGE-ME" not in k[0]), "")
st, body = http("GET", "/v1/models", token=key)
ids, agg_ids = [], []
if st == 200:
    data = json.loads(body).get("data", [])
    ids = [m["id"] for m in data]
    agg_ids = [m["id"] for m in data if m.get("type") == "aggregation"]
print("/v1/models:", st, "total:", len(ids), "aggregation entries:", agg_ids)
missing = [n for n in expected if n not in ids]
print("aggregations missing from /v1/models:", missing)

ok = (st == 200 and auto_off and not auto_found and has_groups and not missing)
print("SMOKE_OK" if ok else "SMOKE_FAIL")
'''


def _skip_backend(rel_posix: str) -> bool:
    """排除数据库、虚拟环境、日志、缓存（这些不能从本地覆盖到生产）"""
    parts = rel_posix.split("/")
    if any(p in (".venv", "__pycache__", "logs") for p in parts):
        return True
    name = parts[-1]
    return name.startswith("smart_router.db") or name.startswith("demo.db")


def make_archive(local_root: str, out_path: str, skip=None) -> int:
    count = 0
    with tarfile.open(out_path, "w:gz") as tar:
        for root, dirs, files in os.walk(local_root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, local_root).replace(os.sep, "/")
                if skip and skip(rel):
                    continue
                tar.add(full, arcname=rel)
                count += 1
    return count


def run(client, cmd, timeout=240) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return "\n".join(x for x in (out, err) if x) or "(空)"


def step(title: str) -> None:
    print(f"\n[{title}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只生成本地清单，不连接服务器")
    ap.add_argument("--migrate-only", action="store_true", help="只备份 + 传 sql + 跑迁移，不动代码")
    args = ap.parse_args()

    if not os.path.isdir(LOCAL_DIST):
        print(f"!! 前端产物不存在：{LOCAL_DIST}\n   请先在 frontend/ 执行 npm run build")
        return 1

    tmpdir = tempfile.mkdtemp(prefix="sr_deploy_")
    tgz_backend = os.path.join(tmpdir, "backend.tgz")
    tgz_sql = os.path.join(tmpdir, "sql.tgz")
    tgz_dist = os.path.join(tmpdir, "dist.tgz")

    step("0 打包本地产物")
    n_backend = make_archive(LOCAL_BACKEND, tgz_backend, _skip_backend)
    n_sql = make_archive(LOCAL_SQL, tgz_sql)
    n_dist = make_archive(LOCAL_DIST, tgz_dist)
    print(f"  backend: {n_backend} 文件 / {os.path.getsize(tgz_backend)/1024:.0f} KB")
    print(f"  sql:     {n_sql} 文件 / {os.path.getsize(tgz_sql)/1024:.0f} KB")
    print(f"  dist:    {n_dist} 文件 / {os.path.getsize(tgz_dist)/1024:.0f} KB")

    if args.dry_run:
        print("\n--dry-run 结束，未连接服务器。")
        return 0

    if not PASS:
        print("  SR_SSH_PASS 未设置，尝试本机 SSH 密钥认证")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, 22, USER, PASS or None, timeout=15)
    except paramiko.AuthenticationException as e:
        print(f"!! SSH 认证失败：{e}")
        return 1
    sftp = client.open_sftp()
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{REMOTE_BACKUP}/{ts}"
    print(f"  已连接 {HOST}（备份目录 {backup_dir}）")

    try:
        # ---------- 1 备份 ----------
        step("1 备份生产数据库（sqlite3 在线备份）+ 旧代码 + 旧前端")
        print(run(client, f"mkdir -p {backup_dir}"))
        db_backup = (
            "import sqlite3\n"
            f"src = sqlite3.connect('{REMOTE_DB}')\n"
            f"dst = sqlite3.connect('{backup_dir}/smart_router.db')\n"
            "src.backup(dst)\n"
            "src.close(); dst.close()\n"
            "print('DB_BACKUP_OK')\n"
        )
        out = run(client, f"{REMOTE_PY} - <<'PYEOF'\n{db_backup}\nPYEOF")
        print(out)
        if "DB_BACKUP_OK" not in out:
            print("\n!! 数据库备份失败，已中止（未做任何改动）")
            return 2
        print(run(client,
                  f"cd {REMOTE_ROOT} && tar czf {backup_dir}/backend_code.tar.gz "
                  "--exclude='backend/smart_router.db*' --exclude='backend/.venv' "
                  "--exclude='*__pycache__*' --exclude='backend/logs' --exclude='backend/demo.db*' "
                  "backend sql frontend_dist && echo CODE_BACKUP_OK"))
        print(run(client, f"ls -lh {backup_dir}"))

        # ---------- 2 上传 sql ----------
        step("2 上传 sql 整树（迁移脚本必须在服务器上就位）")
        sftp.put(tgz_sql, f"{backup_dir}/sql.tgz")
        print(run(client, f"mkdir -p {REMOTE_SQL} && tar xzf {backup_dir}/sql.tgz -C {REMOTE_SQL} && echo EXTRACT_OK"))
        print("  sql 文件数: " + run(client, f"find {REMOTE_SQL} -name '*.sql' | wc -l"))
        print(run(client, f"chown -R {SERVICE_OWNER}:{SERVICE_OWNER} {REMOTE_SQL}"))

        # ---------- 3 预迁移 ----------
        step("3 预迁移生产库（重启前完成，避免新代码导入期读到不完整表结构）")
        sftp.putfo(io.BytesIO(MIGRATE_HELPER.encode("utf-8")), "/tmp/sr_migrate.py")
        print("  " + run(client, "test -f /tmp/sr_migrate.py && echo HELPER_READY"))
        for rel in MIGRATE_FILES:
            out = run(client, f"{REMOTE_PY} /tmp/sr_migrate.py {REMOTE_DB} {REMOTE_ROOT}/{rel}")
            print(f"  {out}")
            if "APPLIED" not in out:
                print(f"\n!! 迁移失败：{rel} —— 已中止，未替换代码，生产仍用旧版本运行")
                print("   数据库可用第 1 步的备份回滚")
                return 3

        print("  迁移后表结构核对：")
        print(run(client, (
            "cd /opt/smart-router/backend && .venv/bin/python - <<'PYEOF'\n"
            "import sqlite3\n"
            "con = sqlite3.connect('smart_router.db')\n"
            "tabs = sorted(r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\"))\n"
            "print('TABLES:', ','.join(tabs))\n"
            "print('agg_unified rows:', con.execute('SELECT COUNT(*) FROM agg_unified').fetchone()[0])\n"
            "cols = [r[1] for r in con.execute('PRAGMA table_info(agg_unified)')]\n"
            "print('agg_unified cols:', ','.join(cols))\n"
            "print('rule_bindings col:', cols.count('rule_bindings'))\n"
            "print('groups col:', cols.count('groups'))\n"
            "print('log_usage.upstream_model:', [r[1] for r in con.execute('PRAGMA table_info(log_usage)')].count('upstream_model'))\n"
            "print('auto_same_name_aggregate:', con.execute(\"SELECT value FROM sys_setting WHERE key='auto_same_name_aggregate'\").fetchone())\n"
            "print('CH-033 残留空壳行:', con.execute(\n"
            "    \"SELECT COUNT(*) FROM agg_unified WHERE kind='static' AND enabled=0 \"\n"
            "    \"AND remark='已关闭（原自动发现聚合）'\").fetchone()[0])\n"
            "PYEOF"
        )))

        if args.migrate_only:
            print("\n--migrate-only 结束：数据库已迁移，代码与前端未改动。")
            return 0

        # ---------- 4 上传后端 ----------
        step("4 上传并解包后端整树")
        sftp.put(tgz_backend, f"{backup_dir}/backend.tgz")
        print(run(client, f"tar xzf {backup_dir}/backend.tgz -C {REMOTE_BACKEND} && echo EXTRACT_OK"))
        print("  远端 app py 文件数: " +
              run(client, f"find {REMOTE_BACKEND}/app -name '*.py' -not -path '*__pycache__*' | wc -l"))

        # ---------- 5 替换前端 ----------
        step("5 替换前端产物")
        print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo CLEAN_OK"))
        sftp.put(tgz_dist, f"{backup_dir}/dist.tgz")
        print(run(client, f"tar xzf {backup_dir}/dist.tgz -C {REMOTE_DIST} && echo EXTRACT_OK"))
        print("  远端 dist 文件数: " + run(client, f"find {REMOTE_DIST} -type f | wc -l"))

        # ---------- 6 清理 + 属主 ----------
        step("6 清理远端 __pycache__ + 修正文件属主")
        print(run(client,
                  f"find {REMOTE_BACKEND} -name __pycache__ -type d -prune -exec rm -rf {{}} + ; echo PYCACHE_CLEANED"))
        print(run(client,
                  f"chown -R {SERVICE_OWNER}:{SERVICE_OWNER} {REMOTE_BACKEND}/app {REMOTE_BACKEND}/run.py "
                  f"{REMOTE_BACKEND}/seed.py {REMOTE_BACKEND}/pyproject.toml {REMOTE_BACKEND}/uv.lock "
                  f"{REMOTE_DIST} && echo CHOWN_OK"))

        # ---------- 7 语法预检 ----------
        step("7 远端语法预检")
        out = run(client, f"cd {REMOTE_BACKEND} && {REMOTE_PY} -m compileall -q app run.py seed.py && echo COMPILE_OK")
        print(out)
        if "COMPILE_OK" not in out:
            print("\n!! 语法预检未通过，已中止重启。生产仍运行旧代码（数据库已迁移，兼容旧代码）。")
            return 4

        # ---------- 8 重启 + 验证 ----------
        step("8 重启服务 + 健康检查")
        print(run(client, "systemctl restart smart-router && sleep 7 && systemctl is-active smart-router"))
        print(run(client, "curl -s -o /dev/null -w 'GET /            -> %{http_code}\\n' http://127.0.0.1:10002/"))
        print(run(client, "curl -s -o /dev/null -w 'GET /health      -> %{http_code}\\n' http://127.0.0.1:10002/health"))
        print(run(client,
                  "curl -s -o /dev/null -w 'POST /admin/api/login -> %{http_code}\\n' -X POST "
                  "http://127.0.0.1:10002/admin/api/login -H 'Content-Type: application/json' "
                  "-d '{\"username\":\"admin\",\"password\":\"smart-router-2026\"}'"))
        print(run(client,
                  "curl -s -o /dev/null -w 'POST /v1/chat/completions 无Key -> %{http_code}\\n' -X POST "
                  "http://127.0.0.1:10002/v1/chat/completions -H 'Content-Type: application/json' -d '{}'"))

        print("\n===== 启动日志关键行（配置已加载 / 迁移告警 / 异常） =====")
        print(run(client,
                  "journalctl -u smart-router -n 80 --no-pager | grep -E "
                  "'配置已加载|增量结构补齐失败|Traceback|ERROR|启动，监听端口' || echo '(无匹配)'"))

        print("\n===== 最近 25 行日志 =====")
        print(run(client, "journalctl -u smart-router -n 25 --no-pager"))

        # ---------- 9 业务冒烟 ----------
        step("9 业务冒烟（CH-034 聚合分组 / CH-036 自动聚合开关）")
        sftp.putfo(io.BytesIO(SMOKE_SCRIPT.encode("utf-8")), "/tmp/sr_smoke_deploy.py")
        smoke_out = run(client, f"{REMOTE_PY} /tmp/sr_smoke_deploy.py", timeout=120)
        print(smoke_out)
        if "SMOKE_OK" not in smoke_out:
            print("\n!! 冒烟未全部通过 —— 服务已起来，但上述项需人工复核（见备份目录回滚说明）")
            return 5

        print(f"\n部署完成。备份目录：{backup_dir}")
        print(f"回滚代码：cd {REMOTE_ROOT} && tar xzf {backup_dir}/backend_code.tar.gz && "
              f"chown -R {SERVICE_OWNER}:{SERVICE_OWNER} backend && systemctl restart smart-router")
        return 0
    finally:
        sftp.close()
        client.close()


if __name__ == "__main__":
    sys.exit(main())

"""部署前勘察（只读）：连接生产 10.10.0.2 读取现状，不做任何修改。

用途：确认生产端当前版本、文件树、数据库表结构与 systemd 配置，
据此确定本次全量部署需要补齐的文件与迁移。

用法：
    $env:SR_SSH_PASS='<密码>'
    .\\backend\\.venv\\Scripts\\python.exe test\\deploy_probe_prod.py
"""

import os
import sys

import paramiko

HOST = "10.10.0.2"
USER = "root"
# 密码来源优先级：
#   1) 环境变量 SR_SSH_PASS
#   2) 仓库外的本地文件（默认 E:\80-project_dev\.sr_deploy_pass，避免密码进入对话记录）
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

REMOTE_BACKEND = "/opt/smart-router/backend"
REMOTE_SQL = "/opt/smart-router/sql"
REMOTE_DIST = "/opt/smart-router/frontend_dist"

# 生产库结构探查（用服务器自带 python 执行）
# 注意：脚本内部含 % 格式化，故外层用 __BACKEND__ 占位符 + replace，避免与 % 冲突
DB_SNIPPET = """
import json, sqlite3
con = sqlite3.connect("__BACKEND__/smart_router.db")
tabs = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'"))
print("TABLES:", ",".join(tabs))
keys = sorted(r[0] for r in con.execute("SELECT key FROM sys_setting"))
print("SETTINGS:", ",".join(keys))
for t in ("agg_unified", "log_usage", "up_upstream", "agg_probe_config"):
    try:
        cols = ",".join(r[1] for r in con.execute("PRAGMA table_info(%s)" % t))
        print("COLS[%s]: %s" % (t, cols))
    except Exception as e:
        print("COLS[%s]: ERR %s" % (t, e))
counts = {}
for t in ("up_upstream", "api_api_key", "rule_rule", "agg_unified",
          "agg_model_group", "agg_aggregated_name", "agg_probe_config",
          "agg_probe_template", "log_usage", "up_upstream_key"):
    try:
        counts[t] = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    except Exception:
        counts[t] = "missing"
print("ROWS:", json.dumps(counts, ensure_ascii=False))
""".replace("__BACKEND__", REMOTE_BACKEND)

COMMANDS = [
    ("目录结构", f"ls -la {REMOTE_BACKEND}/ && echo '--- root ---' && ls -la /opt/smart-router/"),
    ("后端 py 文件", f"find {REMOTE_BACKEND} -name '*.py' -not -path '*/.venv/*' -not -path '*__pycache__*' | sed 's|{REMOTE_BACKEND}/||' | sort"),
    ("sql 文件", f"find {REMOTE_SQL} -name '*.sql' | sed 's|{REMOTE_SQL}/||' | sort"),
    ("systemd 单元", "systemctl cat smart-router 2>&1"),
    ("服务状态", "systemctl is-active smart-router; systemctl show smart-router -p MainPID,WorkingDirectory,ExecStart 2>&1"),
    ("监听端口", "ss -tlnp | grep -E ':10002' || echo 'not listening'"),
    ("Python 版本", "/opt/smart-router/backend/.venv/bin/python --version 2>&1"),
    ("依赖包", "/root/miniconda3/bin/pip list 2>/dev/null | grep -iE 'fastapi|uvicorn|httpx|starlette|pydantic' "),
    ("本地健康检查", "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"),
    ("前端产物", f"ls {REMOTE_DIST} 2>&1 | head -10; find {REMOTE_DIST} -type f 2>/dev/null | wc -l"),
    ("磁盘", "df -h / | tail -1"),
]


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return out or err or "(空)"


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        # PASS 为空时 paramiko 会自动尝试本机 SSH 密钥 / agent
        client.connect(HOST, 22, USER, PASS or None, timeout=15)
    except paramiko.AuthenticationException as e:
        print(f"!! SSH 认证失败：{e}\n   请设置环境变量 SR_SSH_PASS，或在本机配置可登录的 SSH 密钥")
        return 1
    print(f"已连接 {HOST}\n")

    for title, cmd in COMMANDS:
        print(f"===== {title} =====")
        print(run(client, cmd))
        print()

    print("===== 数据库探查 =====")
    print(run(client, f"/opt/smart-router/backend/.venv/bin/python - <<'PYEOF'\n{DB_SNIPPET}\nPYEOF"))

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

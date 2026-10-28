"""CH-051 部署：聚合测试 + 成员加权分发（v5.3.0）

用法：
    $env:SR_SSH_PASS='<SSH密码>'
    $env:SR_ADMIN_PASS='<后台密码>'
    python test/deploy_ch051.py

只传本轮改动：后端 6 个文件 + 新的前端 dist（整目录替换）；不跑 SQL（无表结构变化）。
步骤：备份 → 后端文件 → 前端 dist → 清 pycache/chown → 重启 → 冒烟（版本/健康/登录/聚合测试两连测）。
"""

import os
import sys
import tarfile
import time

import paramiko

HOST = "10.10.0.2"
USER = "root"
SSH_PASS = os.environ.get("SR_SSH_PASS", "")
ADMIN_PASS = os.environ.get("SR_ADMIN_PASS", "")
REMOTE_ROOT = "/opt/smart-router"
REMOTE_BACKEND = f"{REMOTE_ROOT}/backend"
REMOTE_DIST = f"{REMOTE_ROOT}/frontend_dist"
OWNER = "wjz666123"
PY = f"{REMOTE_BACKEND}/.venv/bin/python"

LOCAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_FILES = [
    "backend/app/core/weighted_rr.py",
    "backend/app/services/router_service.py",
    "backend/app/api/admin/aggregations.py",
    "backend/app/main.py",
    "backend/run.py",
    "backend/pyproject.toml",
]


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


def main() -> int:
    if not SSH_PASS:
        print("缺少 SR_SSH_PASS")
        return 2
    if not ADMIN_PASS:
        print("缺少 SR_ADMIN_PASS（后台管理员密码，用于冒烟登录）")
        return 2

    dist_dir = os.path.join(LOCAL_ROOT, "frontend", "dist")
    if not os.path.isdir(dist_dir):
        print("frontend/dist 不存在，先 npm run build")
        return 2
    dist_tgz = os.path.join(LOCAL_ROOT, "backend", ".tmp_ch051_dist.tar.gz")
    with tarfile.open(dist_tgz, "w:gz") as tf:
        for name in os.listdir(dist_dir):
            tf.add(os.path.join(dist_dir, name), arcname=name)
    print(f"dist 打包完成：{os.path.getsize(dist_tgz) / 1024:.0f} KB")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, 22, USER, SSH_PASS, timeout=20)
    print(f"已连接 {USER}@{HOST}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{REMOTE_ROOT}/backup/ch051-{ts}"

    # 1) 备份
    run(client, f"mkdir -p {backup_dir}")
    run(client, f"cd {REMOTE_ROOT} && tar czf {backup_dir}/backend_code.tar.gz "
                f"backend/app backend/run.py backend/pyproject.toml && echo BACKEND_BAK_OK")
    run(client, f"cd {REMOTE_ROOT} && tar czf {backup_dir}/frontend_dist.tar.gz frontend_dist && echo DIST_BAK_OK")
    run(client, f"du -sh {backup_dir}")

    # 2) 后端文件
    sftp = client.open_sftp()
    for rel in BACKEND_FILES:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        if not os.path.exists(local):
            raise SystemExit(f"本地文件不存在：{local}")
        tmp = f"/tmp/ch051_{os.path.basename(rel)}"
        sftp.put(local, tmp)
        run(client, f"mkdir -p {REMOTE_ROOT}/{os.path.dirname(rel)} && "
                    f"mv -f {tmp} {REMOTE_ROOT}/{rel}")
    # 3) 前端 dist
    sftp.put(dist_tgz, "/tmp/ch051_dist.tar.gz")
    sftp.close()
    run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && "
                f"tar xzf /tmp/ch051_dist.tar.gz -C {REMOTE_DIST} && rm -f /tmp/ch051_dist.tar.gz && "
                f"echo DIST_OK && ls {REMOTE_DIST} | head -5")

    # 4) 清理与属主
    run(client, f"find {REMOTE_BACKEND}/app -name __pycache__ -type d -prune -exec rm -rf {{}} + ; echo PYCACHE_CLEAN")
    run(client, f"chown -R {OWNER}:{OWNER} {REMOTE_BACKEND}/app {REMOTE_BACKEND}/run.py "
                f"{REMOTE_BACKEND}/pyproject.toml {REMOTE_DIST} && echo CHOWN_OK")

    # 5) 重启 + 版本
    run(client, "systemctl restart smart-router && sleep 8 && systemctl is-active smart-router")
    run(client, "curl -s -o /dev/null -w 'GET /health -> %{http_code}\\n' http://127.0.0.1:10002/health")
    run(client, "curl -s http://127.0.0.1:10002/openapi.json | head -c 120")

    # 6) 冒烟：登录 + 聚合列表 + 测试端点两连测（验证权重轮换）
    smoke = f"""
import json, urllib.request

BASE = 'http://127.0.0.1:10002'

def req(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8', 'ignore'))

st, login = req('/admin/api/login', 'POST', {{'username': 'admin', 'password': '{ADMIN_PASS}'}})
print('login:', st, bool(login.get('token')))
token = login['token']

st, aggs = req('/admin/api/aggregations', token=token)
names = [a['name'] for a in aggs.get('aggregations', [])]
print('aggregations:', st, len(names))

served = []
for i in range(2):
    st, res = req('/admin/api/aggregations/test?name=deepseek-v4-1-flash', 'POST',
                  {{'prompt': '只回复ok', 'include_aggregate': True}}, token)
    served.append((res.get('aggregate') or {{}}).get('served', {{}}).get('model'))
    print('test#%d:' % (i + 1), st, 'members=%s' % res.get('summary'),
          'served=%s' % served[-1])
print('rotation_ok:', served[0] != served[1], served)
"""
    run(client, f"cd {REMOTE_BACKEND} && {PY} - <<'PYEOF'\n{smoke}\nPYEOF")

    # 7) 前端产物含新功能
    run(client, f"grep -rl '测试聚合' {REMOTE_DIST}/assets | head -3; "
                f"ls {REMOTE_DIST}/assets | grep -c '^Aggregated-'")

    # 8) 日志无异常
    run(client, "journalctl -u smart-router -n 30 --no-pager | grep -E '启动|配置已加载|ERROR|Traceback' || true")

    os.remove(dist_tgz)
    print(f"\n部署完成：备份 {backup_dir}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

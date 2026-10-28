"""CH-050 热修复部署：中文上游 ID 响应头 → /v1 500（UnicodeEncodeError）

用法：
    $env:SR_SSH_PASS='<密码>'
    python test/deploy_ch050_hotfix.py

只改后端 6 个文件（含 1 个新文件），不重建前端、不动数据库：
    backend/app/upstream/headers.py          （新增）
    backend/app/upstream/openai_adapter.py
    backend/app/services/router_service.py
    backend/app/api/v1/messages.py
    backend/app/api/v1/responses.py
    backend/app/main.py
    backend/run.py
    backend/pyproject.toml

步骤：备份原文件 → 上传 → 清 pycache → chown → 重启 → 冒烟（health / 版本 / 头部编码自检）
每步失败即中止，中止点尽量落在「替换代码之前」。
"""

import os
import sys
import tarfile
import time

import paramiko

HOST = "10.10.0.2"
USER = "root"
PASS = os.environ.get("SR_SSH_PASS", "")
REMOTE_ROOT = "/opt/smart-router"
REMOTE_BACKEND = f"{REMOTE_ROOT}/backend"
REMOTE_PY = f"{REMOTE_BACKEND}/.venv/bin/python"
OWNER = "wjz666123"

LOCAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    "backend/app/upstream/headers.py",
    "backend/app/upstream/openai_adapter.py",
    "backend/app/services/router_service.py",
    "backend/app/api/v1/messages.py",
    "backend/app/api/v1/responses.py",
    "backend/app/main.py",
    "backend/run.py",
    "backend/pyproject.toml",
]


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    code = stdout.channel.recv_exit_status()
    text = (out + ("\n" + err if err else "")).strip()
    print(f"$ {cmd}\n  {text[:1200]}" if text else f"$ {cmd}")
    if code != 0:
        raise SystemExit(f"命令失败（exit={code}）：{cmd}")
    return text


def main() -> int:
    if not PASS:
        print("缺少 SR_SSH_PASS：先 $env:SR_SSH_PASS='<密码>' 再运行")
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, 22, USER, PASS, timeout=20)
    print(f"已连接 {USER}@{HOST}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{REMOTE_ROOT}/backup/ch050-{ts}"

    # 1) 备份将要覆盖的文件
    run(client, f"mkdir -p {backup_dir}")
    names = " ".join(f for f in FILES)
    run(client, f"cd {REMOTE_ROOT} && tar czf {backup_dir}/ch050_files.tar.gz {names} 2>/dev/null; "
                 f"ls -la {backup_dir}")

    # 2) 上传
    sftp = client.open_sftp()
    for rel in FILES:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        remote_tmp = f"/tmp/ch050_{os.path.basename(rel)}"
        sftp.put(local, remote_tmp)
        run(client, f"mkdir -p {os.path.dirname(REMOTE_ROOT + '/' + rel)} && "
                    f"mv -f {remote_tmp} {REMOTE_ROOT}/{rel}")
    sftp.close()

    # 3) 清缓存 + 属主
    run(client, f"find {REMOTE_BACKEND}/app -name __pycache__ -type d -prune -exec rm -rf {{}} + ; echo PYCACHE_CLEAN")
    run(client, f"chown -R {OWNER}:{OWNER} {REMOTE_BACKEND}/app {REMOTE_BACKEND}/run.py "
                f"{REMOTE_BACKEND}/pyproject.toml && echo CHOWN_OK")

    # 4) 重启 + 状态
    run(client, "systemctl restart smart-router && sleep 7 && systemctl is-active smart-router")
    run(client, "curl -s -o /dev/null -w 'GET /health -> %{http_code}\\n' http://127.0.0.1:10002/health")
    run(client, "curl -s http://127.0.0.1:10002/openapi.json | head -c 200")

    # 5) 头部编码自检（远程 venv 内执行，不依赖任何 Key）
    check = f"""
import json
from starlette.responses import JSONResponse
from app.upstream.headers import ascii_header_value
h = {{'X-Served-By': ascii_header_value('星-国模013/deepseek-flash'), 'X-Retry-Count': '0'}}
r = JSONResponse(status_code=200, content={{'ok': 1}}, headers=h)
print('HEADER_OK', h['X-Served-By'], 'raw_ascii=', all(v.decode('latin-1').isascii() for _, v in r.raw_headers))
"""
    run(client, f"cd {REMOTE_BACKEND} && {REMOTE_PY} - <<'PYEOF'\n{check}\nPYEOF")

    # 6) 启动日志确认
    run(client, "journalctl -u smart-router -n 15 --no-pager | grep -E '启动|配置已加载|ERROR' || true")

    print(f"\n部署完成：备份 {backup_dir}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

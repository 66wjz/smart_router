"""CH-011 增量部署：上传 5 个变更后端文件 + 前端 dist，重启 smart-router 并验证

不触碰生产数据库（只上传指定代码文件；frontend_dist 整体替换不影响 DB）。
"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
    r"app\repositories\upstream_repo.py",
    r"app\core\config.py",
    r"app\services\router_service.py",
    r"app\api\admin\upstreams.py",
    r"app\schemas\upstream.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
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
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传 5 个后端变更文件")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 替换前端 dist")
    print(run(client, f"rm -rf {REMOTE_DIST} && mkdir -p {REMOTE_DIST} && echo cleaned"))
    upload_dir(sftp, LOCAL_DIST, REMOTE_DIST)
    print(f"  dist 文件数: {run(client, f'find {REMOTE_DIST} -type f | wc -l')}")

    print("[3] 语法预检（服务器侧 py_compile）")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/repositories/upstream_repo.py app/core/config.py app/services/router_service.py "
                      "app/api/admin/upstreams.py app/schemas/upstream.py && echo COMPILE_OK"))

    print("[4] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "ss -tlnp | grep 10002 || echo '10002 未监听'"))

    print("[5] 生产验证")
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))
    login = run(client, "curl -s -X POST http://127.0.0.1:10002/admin/api/login "
                        "-H 'Content-Type: application/json' "
                        "-d '{\"username\":\"admin\",\"password\":\"smart-router-2026\"}'")
    token = ""
    try:
        import json
        token = json.loads(login).get("token", "")
    except Exception:
        pass
    print(f"  登录: {'OK' if token else 'FAIL ' + login[:120]}")
    if token:
        print(run(client, f"curl -s http://127.0.0.1:10002/admin/api/upstreams -H 'Authorization: Bearer {token}' | head -c 400"))

    print("[6] 服务日志尾部")
    print(run(client, "journalctl -u smart-router -n 6 --no-pager | tail -6"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

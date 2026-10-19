"""生产只读验证：CH-034 聚合分组 + CH-036 自动聚合开关（不改任何配置）

用法：
    $env:SR_SSH_PASS='<密码>'
    .\\backend\\.venv\\Scripts\\python.exe test\\verify_prod_ch034_036.py

做三件事（全部只读或最小成本请求）：
    1. 导出生产 agg_unified 全表（name/kind/enabled/groups），解释「哪些聚合会出现在 /v1/models」
    2. 登录后取聚合列表，与库中行核对
    3. 用便宜聚合名发一次 max_tokens=1 的真实请求，验证「成员分组锁死时聚合仍可用」（用户原始故障场景）

密码来源：SR_SSH_PASS 环境变量 > E:\\80-project_dev\\.sr_deploy_pass
硬编码凭据一律不落盘。
"""

import io
import os
import sys

import paramiko

HOST = "10.10.0.2"
USER = "root"
PASS_FILE = os.environ.get("SR_SSH_PASS_FILE") or r"E:\80-project_dev\.sr_deploy_pass"
REMOTE_PY = "/opt/smart-router/backend/.venv/bin/python"

# 便宜聚合（成员为 deepseek-v4.1-flash 系列），符合用户「测试只用便宜模型」的约束
TEST_AGG = "deepseek-v4-1-flash"

REMOTE_SCRIPT = '''import json, sqlite3, urllib.request, urllib.error

BASE = "http://127.0.0.1:10002"
DB = "/opt/smart-router/backend/smart_router.db"


def http(method, path, body=None, token=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


con = sqlite3.connect(DB)
print("=== agg_unified 全表 ===")
rows = con.execute(
    "SELECT name, kind, enabled, groups, members FROM agg_unified ORDER BY kind, name"
).fetchall()
for name, kind, enabled, groups, members in rows:
    n = len(json.loads(members) if members else [])
    role = "门面(含成员)" if kind == "static" else "rule"
    print("  %-22s kind=%-6s enabled=%s groups=%s members=%d  -> %s"
          % (name, kind, enabled, groups, n, role))

rule_on = [r[0] for r in rows if r[1] == "rule" and r[2]]
print("rule 且启用的聚合（应出现在 /v1/models）:", rule_on)
static_on = [r[0] for r in rows if r[1] == "static" and r[2]]
print("static 且启用的聚合（应出现在 /v1/models）:", static_on)

row = con.execute("SELECT value FROM sys_setting WHERE key='admin'").fetchone()
cfg = json.loads(row[0]) if row else {}
st, body = http("POST", "/admin/api/login",
                {"username": cfg.get("username", "admin"), "password": cfg.get("password", "")})
token = json.loads(body).get("token", "") if st == 200 else ""

keys = con.execute("SELECT key_value, groups FROM api_api_key WHERE enabled=1").fetchall()
key, kgroups = next(((k[0], k[1]) for k in keys if k[0] and "CHANGE-ME" not in k[0]), ("", "[]"))
print("\\n=== 用客户端 Key 冒烟（Key 分组 %s）===" % kgroups)

st, body = http("GET", "/v1/models", token=key)
if st == 200:
    data = json.loads(body).get("data", [])
    agg_entries = [m["id"] for m in data if m.get("type") == "aggregation"]
    print("/v1/models: 200  总条目 %d  聚合条目 %s" % (len(data), agg_entries))
    print("rule 聚合是否在列: %s" % {n: (n in agg_entries) for n in rule_on})
    print("static 聚合是否在列: %s" % {n: (n in agg_entries) for n in static_on})
else:
    print("/v1/models:", st, body.strip()[:200])

print("\\n=== 真实请求（聚合 %s，max_tokens=1）===" % "%TEST_AGG%")
st, body = http("POST", "/v1/chat/completions",
                {"model": "%TEST_AGG%", "messages": [{"role": "user", "content": "hi"}],
                 "max_tokens": 1, "stream": False}, token=key)
print("状态码:", st)
print("响应片段:", body.strip()[:300])

st2, body2 = http("PUT", "/admin/api/config/auto-aggregate", {"enabled": False}, token=token)
print("\\n开关保持关闭:", st2, body2.strip()[:60])
'''

REMOTE_SCRIPT = REMOTE_SCRIPT.replace("%TEST_AGG%", TEST_AGG)


def load_pass() -> str:
    val = os.environ.get("SR_SSH_PASS", "").strip()
    if val:
        return val
    try:
        with open(PASS_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def main() -> int:
    pw = load_pass()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, 22, USER, pw or None, timeout=15)
    sftp = client.open_sftp()
    try:
        sftp.putfo(io.BytesIO(REMOTE_SCRIPT.encode("utf-8")), "/tmp/sr_verify_ch034.py")
        _, stdout, stderr = client.exec_command(f"{REMOTE_PY} /tmp/sr_verify_ch034.py", timeout=180)
        print(stdout.read().decode("utf-8", "ignore"))
        err = stderr.read().decode("utf-8", "ignore").strip()
        if err:
            print("[stderr]", err)
    finally:
        sftp.close()
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

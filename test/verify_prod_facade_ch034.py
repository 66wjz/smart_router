"""生产只读验证（决定性）：CH-034 门面语义 vs 成员级保护

场景要求：同一个 Key，直连某个成员真实模型名被拒（403），走聚合名却成功（200）。

关键前提：该模型名**只能存在于 Key 无权访问的源**里。若它同时存在于 Key 有权限的源
（例如 dsh 里保留了同名模型），直连会走那条路成功，场景就不成立——脚本会先做这个筛查，
自动挑出唯一归属 no_single_use 源的成员模型，挑不到就如实报告。

用法：
    $env:SR_SSH_PASS='<密码>'
    .\\backend\\.venv\\Scripts\\python.exe test\\verify_prod_facade_ch034.py

只发 max_tokens=1 的最小请求（便宜聚合成员）。
"""

import io
import os
import sys

import paramiko

HOST = "10.10.0.2"
USER = "root"
PASS_FILE = os.environ.get("SR_SSH_PASS_FILE") or r"E:\80-project_dev\.sr_deploy_pass"
REMOTE_PY = "/opt/smart-router/backend/.venv/bin/python"

REMOTE_SCRIPT = r'''import json, sqlite3, urllib.request, urllib.error

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

# 上游源 → 分组集合、模型集合
up_groups, up_models = {}, {}
for uid, groups, group_name, models in con.execute(
        "SELECT upstream_id, groups, group_name, models FROM up_upstream WHERE enabled=1"):
    up_groups[uid] = json.loads(groups) if groups else ([group_name] if group_name else [])
    up_models[uid] = [m.get("name") for m in (json.loads(models) if models else [])]

print("=== 启用的上游源 ===")
for uid in up_models:
    print("  %-14s groups=%-22s models=%d" % (uid, up_groups[uid], len(up_models[uid])))

# 客户端 Key 与分组
keys = []
for kv, groups in con.execute("SELECT key_value, groups FROM api_api_key WHERE enabled=1"):
    if kv and "CHANGE-ME" not in kv:
        keys.append((kv, json.loads(groups) if groups else ["free"]))
# 优先挑「不含 no_single_use」的 Key（最能体现被锁住的成员源）
keys.sort(key=lambda t: "no_single_use" in t[1])
kv, kg = keys[0]
print("\n使用 Key 分组:", kg)

# 扫描全部启用的 static 聚合，找出「成员模型只存在于 Key 无权访问的源」的组合
cases = []
aggs = con.execute(
    "SELECT name, members FROM agg_unified WHERE kind='static' AND enabled=1 ORDER BY name"
).fetchall()
print("\n=== 成员归属筛查（找可构造干净场景的聚合）===")
for agg_name, members_raw in aggs:
    members = json.loads(members_raw) if members_raw else []
    locked = []
    for m in members:
        name, uid = m["model"], m["upstream"]
        owners = [u for u, ms in up_models.items() if name in ms]
        accessible = [u for u in owners if not set(up_groups[u]).isdisjoint(set(kg))]
        if not accessible:
            locked.append(name)
    mark = "← 可构造" if locked else ""
    print("  %-20s 成员 %d，其中【仅无权源可访问】%d %s"
          % (agg_name, len(members), len(locked), mark))
    if locked:
        cases.append((agg_name, locked[0]))

if not cases:
    print("\n!! 现有数据下找不到干净场景：每个聚合成员的模型名都同时存在于 Key 可访问的源")
    print("   根因：dsh（premium 分组，%d 个模型）与 no_single_use 各源存在同名模型" % len(up_models.get("dsh", [])))
    print("   含义：no_single_use 这道锁在**数据层面**目前是失效的 —— 任何有 premium 的 Key")
    print("         都能通过 dsh 直连这些模型；要让它生效，需从 dsh 移除这些重复模型")
    print("   （CH-034 的门面逻辑本身已部署并用单元测试覆盖，与此无关）")
else:
    agg_name, name = cases[0]
    print("\n=== 决定性验证（聚合 %s / 成员 %s 仅归属无权源）===" % (agg_name, name))

    st, body = http("POST", "/v1/chat/completions",
                    {"model": name, "messages": [{"role": "user", "content": "hi"}],
                     "max_tokens": 1, "stream": False}, token=kv)
    print("1) 直连真实模型名 -> %s" % st)
    if st != 200:
        print("   拒绝文案:", body.strip()[:170])

    st2, body2 = http("POST", "/v1/chat/completions",
                      {"model": agg_name, "messages": [{"role": "user", "content": "hi"}],
                       "max_tokens": 1, "stream": False}, token=kv)
    print("2) 走聚合名 -> %s" % st2)
    if st2 == 200:
        print("   实际命中上游模型:", json.loads(body2).get("model"))
    else:
        print("   响应:", body2.strip()[:200])

    print("\n结论: %s" % ("✅ 门面语义生效：直连被 403 拦住，走聚合 200 成功"
                        if st == 403 and st2 == 200 else "❌ 与预期不符，需人工复核"))
'''


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
        sftp.putfo(io.BytesIO(REMOTE_SCRIPT.encode("utf-8")), "/tmp/sr_facade_ch034.py")
        _, stdout, stderr = client.exec_command(f"{REMOTE_PY} /tmp/sr_facade_ch034.py", timeout=180)
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

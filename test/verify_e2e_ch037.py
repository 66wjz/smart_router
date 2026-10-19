"""CH-037 真实端到端验证：本地起 smart-router 服务，上游接本机 DSH 网关（8326）

与 verify_role_normalize_ch037.py 的区别：
    那个用 mock 上游，只证明「网关改了 role」；
    这个用**真实的 DSH 网关**，证明「改完之后真的能通」。

链路：
    本脚本 --HTTP--> 本地 smart-router(临时端口) --HTTP--> 127.0.0.1:8326（DSH 网关）

用法：
    python test/verify_e2e_ch037.py

前置：本机 DSH 网关在 8326 监听（已确认），api-key 在 ~/.dsh/openai-gateway/api-key
不触碰 demo.db / 生产库，全部使用临时库。
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
TMPDIR = os.path.join(BACKEND, ".tmp_ch037_e2e")
DB_PATH = os.path.join(TMPDIR, "e2e.db")
PORT = 10197
BASE = f"http://127.0.0.1:{PORT}"
GW = "http://127.0.0.1:8326"
MODEL = "commandgo/deepseek/deepseek-v4.1-flash"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def gw_key() -> str:
    path = os.path.join(os.path.expanduser("~"), ".dsh", "openai-gateway", "api-key")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def prepare_db(key: str) -> None:
    os.makedirs(TMPDIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    sql_files = [
        "01_建表.sql",
        "increment/01_增量_20260809_上游源禁用.sql",
        "increment/02_增量_20260809_上游Key池.sql",
        "increment/03_增量_20260809_上游模型列表.sql",
        "increment/04_增量_20260810_智能重试开关.sql",
        "increment/05_增量_20260811_上游多分组.sql",
        "06_用量统计与自动聚合.sql",
        "increment/06_增量_20261017_聚合探测配置.sql",
        "increment/07_增量_20261017_聚合统一与探测模板.sql",
        "increment/08_增量_20261017_聚合规则绑定.sql",
        "increment/09_增量_20261018_聚合分组.sql",
        "increment/10_增量_20261018_自动聚合开关默认关闭.sql",
    ]
    conn = sqlite3.connect(DB_PATH)
    for rel in sql_files:
        with open(os.path.join(ROOT, "sql", rel.replace("/", os.sep)), encoding="utf-8") as f:
            try:
                conn.executescript(f.read())
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
    conn.commit()

    # 上游源：指向本机真实 DSH 网关
    conn.execute(
        "INSERT INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, "
        "groups, probe_enabled, models, smart_retry, enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("localgw", "本机 DSH 网关", GW, key, "openai", "free", '["free"]', 0,
         json.dumps([{"name": MODEL, "enabled": 1, "order": 0}], ensure_ascii=False), 0, 1),
    )
    conn.execute(
        "INSERT INTO up_upstream_key (upstream_id, api_key, enabled) VALUES (?,?,1)",
        ("localgw", key),
    )
    # 客户端 Key
    conn.execute(
        "INSERT INTO api_api_key (name, key_value, groups, enabled) VALUES (?,?,?,1)",
        ("e2e", "sk-e2e-ch037", '["free"]'),
    )
    conn.commit()
    conn.close()


def wait_ready(timeout: float = 40) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.6)
    return False


def call(label: str, messages: list, stream: bool = False) -> tuple[int, str]:
    body = {"model": MODEL, "messages": messages, "max_tokens": 8}
    if stream:
        body["stream"] = True
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer sk-e2e-ch037")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read(400).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "ignore")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    if not port_open(8326):
        print("!! 本机 DSH 网关 8326 未监听，无法做真实端到端验证")
        return 1
    if port_open(PORT):
        print(f"!! 端口 {PORT} 已被占用，请先释放")
        return 1

    key = gw_key()
    print(f"网关: {GW}   Key 前缀: {key[:8]}…   模型: {MODEL}")

    print("\n[0] 基线：绕过 smart-router 直连网关")
    req = urllib.request.Request(
        GW + "/v1/chat/completions",
        data=json.dumps({"model": MODEL, "max_tokens": 8, "messages": [
            {"role": "developer", "content": "hi"}, {"role": "user", "content": "hi"}]}).encode(),
        method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            print(f"  直连 developer -> {r.status}（若为 200 说明网关已支持，本修复不必要）")
            baseline_400 = r.status != 200
    except urllib.error.HTTPError as e:
        msg = e.read(200).decode("utf-8", "ignore")
        print(f"  直连 developer -> {e.code}  {msg[:150]}")
        baseline_400 = e.code == 400
    except Exception as e:
        print(f"  直连 developer -> ERR {e}")
        baseline_400 = False

    print("\n[1] 准备临时库并启动本地 smart-router 服务")
    prepare_db(key)
    env = dict(os.environ)
    env["SMART_ROUTER_DB"] = DB_PATH
    log_path = os.path.join(TMPDIR, "server.log")
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=BACKEND, env=env, stdout=log_f, stderr=subprocess.STDOUT,
    )
    try:
        ready = wait_ready()
        check(ready, f"服务已在 {PORT} 就绪（pid={proc.pid}）")
        if not ready:
            print("  服务日志尾部：")
            log_f.flush()
            with open(log_path, encoding="utf-8", errors="ignore") as f:
                print("\n".join(f.read().splitlines()[-25:]))
            return 1

        print("\n[2] 经 smart-router：system 角色（基线）")
        st, body = call("system", [{"role": "system", "content": "hi"},
                                   {"role": "user", "content": "hi"}])
        check(st == 200, f"system -> {st}")

        print("\n[3] 经 smart-router：developer 角色（本次修复目标）")
        st, body = call("developer", [{"role": "developer", "content": "hi"},
                                      {"role": "user", "content": "hi"}])
        check(st == 200, f"非流式 developer -> {st}")
        if st != 200:
            print("   响应:", body[:220])
        else:
            check("unsupported message role" not in body, "响应中没有 role 不支持错误")

        print("\n[4] 经 smart-router：developer + 流式")
        st, body = call("developer-stream", [{"role": "developer", "content": "hi"},
                                             {"role": "user", "content": "hi"}], stream=True)
        check(st == 200, f"流式 developer -> {st}")
        if st != 200:
            print("   响应:", body[:220])

        print("\n[5] 服务日志确认角色已改写")
        log_f.flush()
        with open(log_path, encoding="utf-8", errors="ignore") as f:
            logs = f.read()
        check("unsupported message role" not in logs, "服务日志无 role 不支持错误")

        if baseline_400:
            print("\n结论: 网关直连 developer 会 400，经 smart-router 转发后 200 —— 修复真实生效 ✅")
        else:
            print("\n注意: 直连网关未复现 400，本次链路验证仅证明转发正常")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_f.close()

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

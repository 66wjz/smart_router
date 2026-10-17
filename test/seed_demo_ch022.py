"""
CH-022：生成演示数据库（backend/demo.db）

用途：让用户在不触碰生产/本地正式配置的前提下，直观体验
  - 异名模型聚合（同一模型在多个源里名字不同）
  - 聚合组独立探测配置（开/关、间隔、慢阈值、排序模式、探测时段）
  - 探测计划全局去重
  - 仪表盘的用量分布与趋势

用法：
    python test/seed_demo_ch022.py            # 重建演示库
    python test/seed_demo_ch022.py --keep     # 保留旧库，仅补数据

演示库启动：
    $env:SMART_ROUTER_DB = "backend/demo.db"
    python -c "import uvicorn; from app.main import app; uvicorn.run(app, host='127.0.0.1', port=10198)"
"""

import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(BASE, "backend")
SQL_DIR = os.path.join(BASE, "sql")
DEMO_DB = os.path.join(BACKEND, "demo.db")

random.seed(20261017)

# ------------------------------------------------------------
# 演示配置
# ------------------------------------------------------------

UPSTREAMS = [
    {
        "upstream_id": "buddy", "name": "Buddy 积分池", "base_url": "https://api.buddy-demo.example/v1",
        "format": "openai", "groups": ["free"], "enabled": 1, "probe_enabled": 1, "smart_retry": 1,
        "keys": ["sk-buddy-demo-0001", "sk-buddy-demo-0002"],
        "models": ["deepseek-v4.1-flash", "qwen3-coder-480b", "gemini-2.5-pro"],
    },
    {
        "upstream_id": "loomy", "name": "Loomy 中转", "base_url": "https://api.loomy-demo.example/v1",
        "format": "openai", "groups": ["free"], "enabled": 1, "probe_enabled": 1, "smart_retry": 0,
        "keys": ["sk-loomy-demo-0001"],
        "models": ["DeepSeek-V4.1-Flash", "glm-4.6", "kimi-k2-thinking"],
    },
    {
        "upstream_id": "trae", "name": "Trae 额度池", "base_url": "https://api.trae-demo.example/v1",
        "format": "openai", "groups": ["free", "premium"], "enabled": 1, "probe_enabled": 1, "smart_retry": 1,
        "keys": ["sk-trae-demo-0001", "sk-trae-demo-0002"],
        "models": ["deepseek-v4.1-flash", "qwen3-coder-480b"],
    },
    {
        "upstream_id": "dsh", "name": "DSH 直连", "base_url": "https://api.dsh-demo.example",
        "format": "anthropic", "groups": ["premium"], "enabled": 1, "probe_enabled": 0, "smart_retry": 0,
        "keys": ["sk-ant-demo-0001"],
        "models": ["glm-4.6", "kimi-k2-thinking-v2"],
    },
]

# 聚合组（member: (upstream, 该源真实模型名)）
MODEL_GROUPS = [
    {
        "model": "deepseek-v4-1-flash",
        "members": [
            {"upstream": "buddy", "model": "deepseek-v4.1-flash", "weight": 3},
            {"upstream": "loomy", "model": "DeepSeek-V4.1-Flash", "weight": 2},
            {"upstream": "trae", "model": "deepseek-v4.1-flash", "weight": 1},
        ],
        "enabled": 1,
        # 探测：开 · 60s · 慢阈值 5s · 速度优先 · 工作日 08:00-23:00
        "probe": {
            "enabled": 1, "interval_seconds": 60, "slow_threshold_seconds": 5.0,
            "sort_mode": "latency",
            "schedule": {"mode": "window", "days": [1, 2, 3, 4, 5],
                         "windows": [{"start": "08:00", "end": "23:00"}]},
        },
    },
    {
        "model": "qwen3-coder",
        "members": [
            {"upstream": "buddy", "model": "qwen3-coder-480b", "weight": 2},
            {"upstream": "trae", "model": "qwen3-coder-480b", "weight": 1},
        ],
        "enabled": 1,
        # 探测：开 · 300s · 稳定优先 · 全天候
        "probe": {
            "enabled": 1, "interval_seconds": 300, "slow_threshold_seconds": None,
            "sort_mode": "stable",
            "schedule": {"mode": "always", "days": [], "windows": []},
        },
    },
    {
        "model": "glm-4-6",
        "members": [
            {"upstream": "loomy", "model": "glm-4.6", "weight": 1},
            {"upstream": "dsh", "model": "glm-4.6", "weight": 1},
        ],
        "enabled": 1,
        # 探测：关（对照）
        "probe": {
            "enabled": 0, "interval_seconds": None, "slow_threshold_seconds": None,
            "sort_mode": "stable", "schedule": {"mode": "always", "days": [], "windows": []},
        },
    },
]

# 故意不合并的异名模型（让聚合页出现「疑似同一模型」建议）
# kimi-k2-thinking（loomy）与 kimi-k2-thinking-v2（dsh）→ 归一化后都是 kimi-k2-thinking-v2? 否，
# 归一化只去前缀/大小写/符号，不处理版本后缀，故这里用另一种写法制造建议：
#   loomy: Kimi-K2-Thinking
#   dsh:   kimi.k2.thinking
EXTRA_SUGGEST_MODELS = [
    ("loomy", "Kimi-K2-Thinking"),
    ("dsh", "kimi.k2.thinking"),
]

CLIENT_KEYS = [
    {"name": "free-key", "key_value": "sk-client-demo-free-0001", "groups": ["free"], "enabled": 1},
    {"name": "premium-key", "key_value": "sk-client-demo-premium-0001", "groups": ["free", "premium"], "enabled": 1},
    {"name": "limited-key", "key_value": "sk-client-demo-limited-0001", "groups": ["free"], "enabled": 0},
]

RULES = [
    {
        "name": "默认对话",
        "match": {"default": True},
        "candidates": [
            {"model": "deepseek-v4-1-flash", "upstream": "buddy", "weight": 5, "priority": 1,
             "max_context": 128000, "max_output": 8192},
            {"model": "qwen3-coder", "upstream": "buddy", "weight": 3, "priority": 1,
             "max_context": 256000, "max_output": 16384},
        ],
    },
    {
        "name": "视觉理解",
        "match": {"has_image": True},
        "candidates": [
            {"model": "gemini-2.5-pro", "upstream": "buddy", "weight": 2, "priority": 1,
             "max_context": 1000000, "max_output": 32768},
            {"model": "glm-4-6", "upstream": "loomy", "weight": 1, "priority": 2,
             "max_context": 200000, "max_output": 16384},
        ],
    },
]

PTR = {"name": "best-chat", "target_model": "deepseek-v4-1-flash", "upstream_id": "trae"}

SETTINGS = {
    "latency_probe": {
        "enabled": True, "interval_seconds": 300, "timeout_seconds": 35,
        "request_text": "Hi", "max_tokens": 3, "base_latency": 0.5,
        "down_threshold_seconds": 30, "slow_threshold_seconds": 8,
        "error_as_down": True, "max_concurrency": 5, "count_key_failures": False,
        "schedule": {"mode": "always"},
    },
    "retry": {"max_attempts": 3, "response_timeout": 60, "first_chunk_timeout": 30},
    "failover": {"max_fails": 3, "cooldown_seconds": 120},
    "smart_retry": {"extra_attempts": 2, "backoff_ms": [500, 1500], "jitter": 0.2},
    "admin": {"username": "admin", "password": "smart-router-2026", "session_hours": 24},
    "listen_port": 10198,
    "default_upstream": "buddy",
    "log_level": "INFO",
    "log_routing": True,
    "groups": [
        {"name": "free", "description": "免费分组（默认）"},
        {"name": "premium", "description": "付费分组"},
    ],
    "auto_same_name_aggregate": True,
    "usage_retention_days": 30,
}


# ------------------------------------------------------------
# 建库
# ------------------------------------------------------------

def drop_all(conn: sqlite3.Connection) -> None:
    tables = [
        "rule_candidate", "rule_rule", "api_api_key", "up_upstream_key", "up_upstream",
        "pt_pointer", "agg_aggregated_name", "agg_model_group", "agg_probe_config",
        "agg_unified", "agg_probe_template",
        "log_usage", "sys_setting",
    ]
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


def run_sql(conn: sqlite3.Connection, filename: str) -> None:
    path = os.path.join(SQL_DIR, filename)
    if not os.path.exists(path):
        print(f"  [跳过] {filename}（不存在）")
        return
    with open(path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    print(f"  [SQL ] {filename}")


def seed_upstreams(conn: sqlite3.Connection) -> None:
    for u in UPSTREAMS:
        models = [{"name": m, "enabled": 1, "order": i} for i, m in enumerate(u["models"])]
        # 演示：给 dsh 的 glm-4.6 挂 anthropic 协议
        if u["upstream_id"] == "dsh":
            for m in models:
                if m["name"] == "glm-4.6":
                    m["protocol"] = "anthropic"
        conn.execute(
            "INSERT INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, groups, "
            "probe_enabled, enabled, models, smart_retry) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (u["upstream_id"], u["name"], u["base_url"], u["keys"][0], u["format"],
             u["groups"][0], json.dumps(u["groups"], ensure_ascii=False),
             u["probe_enabled"], u["enabled"], json.dumps(models, ensure_ascii=False), u["smart_retry"]),
        )
        for k in u["keys"]:
            conn.execute(
                "INSERT INTO up_upstream_key (upstream_id, api_key, enabled) VALUES (?,?,1)",
                (u["upstream_id"], k),
            )
    print(f"  [数据] 上游源 {len(UPSTREAMS)} 个（含 Key 池）")


def seed_suggest_models(conn: sqlite3.Connection) -> None:
    """给已有上游追加"未合并的异名模型"，用于演示一键合并建议"""
    for uid, model in EXTRA_SUGGEST_MODELS:
        row = conn.execute("SELECT models FROM up_upstream WHERE upstream_id = ?", (uid,)).fetchone()
        models = json.loads(row[0] or "[]")
        if any(m.get("name") == model for m in models):
            continue
        models.append({"name": model, "enabled": 1, "order": len(models)})
        conn.execute("UPDATE up_upstream SET models = ? WHERE upstream_id = ?",
                     (json.dumps(models, ensure_ascii=False), uid))
    print("  [数据] 追加 2 个未合并异名模型（演示建议合并）")


def seed_groups(conn: sqlite3.Connection) -> None:
    for g in MODEL_GROUPS:
        conn.execute(
            "INSERT INTO agg_model_group (model, upstreams, enabled) VALUES (?,?,?)",
            (g["model"], json.dumps(g["members"], ensure_ascii=False), g["enabled"]),
        )
        p = g["probe"]
        conn.execute(
            "INSERT INTO agg_probe_config (model, enabled, interval_seconds, slow_threshold_seconds, "
            "sort_mode, schedule) VALUES (?,?,?,?,?,?)",
            (g["model"], p["enabled"], p["interval_seconds"], p["slow_threshold_seconds"],
             p["sort_mode"], json.dumps(p["schedule"], ensure_ascii=False)),
        )
    print(f"  [数据] 聚合组 {len(MODEL_GROUPS)} 个（含探测配置：开/开/关）")


def seed_keys_rules(conn: sqlite3.Connection) -> None:
    for k in CLIENT_KEYS:
        conn.execute(
            "INSERT INTO api_api_key (name, key_value, groups, enabled) VALUES (?,?,?,?)",
            (k["name"], k["key_value"], json.dumps(k["groups"]), k["enabled"]),
        )
    for idx, r in enumerate(RULES):
        cur = conn.execute(
            "INSERT INTO rule_rule (name, match_json, sort_order) VALUES (?,?,?)",
            (r["name"], json.dumps(r["match"], ensure_ascii=False), idx),
        )
        rule_id = cur.lastrowid
        for c in r["candidates"]:
            conn.execute(
                "INSERT INTO rule_candidate (rule_id, model, upstream_id, weight, priority, "
                "max_context, max_output) VALUES (?,?,?,?,?,?,?)",
                (rule_id, c["model"], c["upstream"], c["weight"], c["priority"],
                 c.get("max_context"), c.get("max_output")),
            )
    conn.execute(
        "INSERT INTO pt_pointer (name, target_model, upstream_id) VALUES (?,?,?)",
        (PTR["name"], PTR["target_model"], PTR["upstream_id"]),
    )
    print(f"  [数据] 客户端 Key {len(CLIENT_KEYS)} 把 · 路由规则 {len(RULES)} 条 · 别名 1 个")


def seed_settings(conn: sqlite3.Connection) -> None:
    for k, v in SETTINGS.items():
        conn.execute("INSERT OR REPLACE INTO sys_setting (key, value) VALUES (?,?)",
                     (k, json.dumps(v, ensure_ascii=False)))


def seed_agg_names(conn: sqlite3.Connection) -> None:
    for name in ("smart-latest", "smart-chat"):
        conn.execute("INSERT INTO agg_aggregated_name (name) VALUES (?)", (name,))
    print("  [数据] 手写聚合名 2 个")


# 探测模板（CH-023）：挂到聚合上后，聚合自配的探测参数全部失效
PROBE_TEMPLATES = [
    {
        "name": "高频-交易时段",
        "interval_seconds": 60, "slow_threshold_seconds": 5.0, "sort_mode": "latency",
        "schedule": {"mode": "window", "days": [1, 2, 3, 4, 5],
                     "windows": [{"start": "08:00", "end": "23:00"}]},
        "remark": "工作日盘中高频探测，夜间与周末不探",
    },
    {
        "name": "标准-全天",
        "interval_seconds": 300, "slow_threshold_seconds": 8.0, "sort_mode": "stable",
        "schedule": {"mode": "always", "days": [], "windows": []},
        "remark": "5 分钟一轮，稳定优先",
    },
]

# 聚合名 → 模板名（迁移后的 agg_unified 行上挂模板，同时开探测）
AGG_TEMPLATE_BINDING = {
    "deepseek-v4-1-flash": "高频-交易时段",
    "qwen3-coder": "标准-全天",
    "smart-latest": "标准-全天",
}


def seed_templates(conn: sqlite3.Connection) -> None:
    """CH-023：写入探测模板，并把演示聚合挂到模板上"""
    ids: dict[str, int] = {}
    for t in PROBE_TEMPLATES:
        cur = conn.execute(
            "INSERT INTO agg_probe_template (name, interval_seconds, slow_threshold_seconds, "
            "sort_mode, schedule, remark) VALUES (?,?,?,?,?,?)",
            (t["name"], t["interval_seconds"], t["slow_threshold_seconds"], t["sort_mode"],
             json.dumps(t["schedule"], ensure_ascii=False), t["remark"]),
        )
        ids[t["name"]] = cur.lastrowid
    for agg, tpl in AGG_TEMPLATE_BINDING.items():
        conn.execute(
            "UPDATE agg_unified SET template_id = ?, probe_enabled = 1 WHERE name = ?",
            (ids[tpl], agg),
        )
    print(f"  [数据] 探测模板 {len(PROBE_TEMPLATES)} 个，"
          f"{len(AGG_TEMPLATE_BINDING)} 个聚合已挂模板")


# ------------------------------------------------------------
# 用量数据
# ------------------------------------------------------------

# 请求名 → 可能命中的 (upstream, upstream_model, 权重)
ROUTES_FOR_USAGE = [
    # (请求名, [(upstream, 真实模型名, 权重)], (最小 prompt tokens, 最大 prompt tokens))
    ("deepseek-v4-1-flash", [("buddy", "deepseek-v4.1-flash", 5),
                             ("loomy", "DeepSeek-V4.1-Flash", 3),
                             ("trae", "deepseek-v4.1-flash", 2)],
     (420, 900)),
    ("qwen3-coder", [("buddy", "qwen3-coder-480b", 3),
                     ("trae", "qwen3-coder-480b", 2)],
     (700, 1400)),
    ("glm-4-6", [("loomy", "glm-4.6", 2), ("dsh", "glm-4.6", 1)],
     (300, 700)),
    ("smart-latest", [("buddy", "deepseek-v4.1-flash", 4),
                      ("buddy", "qwen3-coder-480b", 2)], (500, 1000)),
    ("best-chat", [("trae", "deepseek-v4.1-flash", 1)], (250, 600)),
    ("gemini-2.5-pro", [("buddy", "gemini-2.5-pro", 1)], (900, 2200)),
    ("Kimi-K2-Thinking", [("loomy", "Kimi-K2-Thinking", 1)], (600, 1800)),
]

UPSTREAM_NAMES = {u["upstream_id"]: u["name"] for u in UPSTREAMS}
CLIENT_KEY_META = [(i + 1, k["name"]) for i, k in enumerate(CLIENT_KEYS)]


def seed_usage(conn: sqlite3.Connection, days: int = 14, base_per_day: int = 110) -> int:
    now = datetime.now()
    total = 0
    rows = []
    for d in range(days - 1, -1, -1):
        day = (now - timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = day.isoweekday()
        # 周末流量打七折
        factor = 0.7 if weekday >= 6 else 1.0
        # 今天只生成到当前时刻
        hours = 24 if d > 0 else max(1, now.hour + 1)
        count = int(base_per_day * factor * hours / 24 * random.uniform(0.85, 1.15))
        for _ in range(count):
            model, routes, (p_lo, p_hi) = random.choices(
                ROUTES_FOR_USAGE, weights=[40, 22, 12, 10, 6, 5, 5], k=1)[0]
            uid, upstream_model, _w = random.choices(routes, weights=[r[2] for r in routes], k=1)[0]
            key_id, key_name = random.choices(CLIENT_KEY_META, weights=[60, 32, 8], k=1)[0]

            hour = random.randint(0, hours - 1) if d > 0 else random.randint(0, max(0, now.hour))
            minute = random.randint(0, 59)
            ts = day.replace(hour=min(hour, 23), minute=minute,
                             second=random.randint(0, 59)).timestamp()
            if ts > now.timestamp():
                ts = now.timestamp() - random.randint(60, 3600)

            prompt = random.randint(p_lo, p_hi)
            completion = random.randint(prompt // 4, prompt // 2)
            failed = random.random() < 0.022
            estimated = random.random() < 0.06
            rows.append((
                ts, key_id, key_name, uid, UPSTREAM_NAMES.get(uid, uid),
                model, upstream_model,
                random.choices(["chat", "anthropic", "responses"], weights=[80, 15, 5], k=1)[0],
                1 if random.random() < 0.55 else 0,
                "error" if failed else "success",
                random.choice([500, 502, 504]) if failed else 200,
                0 if failed else prompt,
                0 if failed else completion,
                0 if failed else prompt + completion,
                1 if estimated else 0,
                random.randint(600, 9000),
                random.randint(120, 900) if random.random() < 0.6 else None,
                random.choice(["upstream 502", "timeout", "connection reset"]) if failed else None,
            ))
    conn.executemany(
        "INSERT INTO log_usage (ts, api_key_id, api_key_name, upstream_id, upstream_name, model, "
        "upstream_model, protocol, stream, status, http_status, prompt_tokens, completion_tokens, "
        "total_tokens, estimated, duration_ms, first_token_ms, error_msg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    total = len(rows)
    print(f"  [数据] 用量记录 {total} 条（近 {days} 天，含约 2% 失败）")
    return total


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------

def main() -> None:
    keep = "--keep" in sys.argv
    print(f"[demo] 目标库: {DEMO_DB}")
    if os.path.exists(DEMO_DB) and not keep:
        for suffix in ("", "-wal", "-shm"):
            p = DEMO_DB + suffix
            if os.path.exists(p):
                os.remove(p)
        print("  [清理] 旧演示库已删除")

    conn = sqlite3.connect(DEMO_DB)
    conn.row_factory = sqlite3.Row
    try:
        # 先清空，再一次性建表（避免 IF NOT EXISTS 留下旧结构）
        drop_all(conn)
        for fn in (
            "01_建表.sql",
            "increment/01_增量_20260809_上游源禁用.sql",
            "increment/02_增量_20260809_上游Key池.sql",
            "increment/03_增量_20260809_上游模型列表.sql",
            "increment/04_增量_20260810_智能重试开关.sql",
            "increment/05_增量_20260811_上游多分组.sql",
            "06_用量统计与自动聚合.sql",
            "increment/06_增量_20261017_聚合探测配置.sql",
            # CH-023：统一聚合 + 探测模板（迁移会自动把上面的旧表数据搬进新表）
            "increment/07_增量_20261017_聚合统一与探测模板.sql",
        ):
            run_sql(conn, fn)

        print("\n[demo] 写入演示数据")
        seed_upstreams(conn)
        seed_suggest_models(conn)
        seed_groups(conn)
        seed_keys_rules(conn)
        seed_settings(conn)
        seed_agg_names(conn)
        # 旧表数据写完后再跑一次 CH-023 迁移，把聚合搬进 agg_unified
        run_sql(conn, "increment/07_增量_20261017_聚合统一与探测模板.sql")
        seed_templates(conn)
        seed_usage(conn)
        conn.commit()
        print("\n[demo] 完成 ✅")
        print(f"  启动演示环境：")
        print(f'    $env:SMART_ROUTER_DB = "{DEMO_DB}"')
        print(f'    cd backend; .\\.venv\\Scripts\\python.exe -c "import uvicorn; '
              f'from app.main import app; uvicorn.run(app, host=\'127.0.0.1\', port=10198)"')
    finally:
        conn.close()


if __name__ == "__main__":
    main()

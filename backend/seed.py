"""
数据库初始化脚本
按依赖顺序执行 sql/ 下的建表、种子与全部增量脚本（幂等：先重建表再导入种子数据）
用法：uv run seed.py

CH-029：支持 SMART_ROUTER_DB 指定目标库；补齐增量 01~08，
否则全新环境只有 01_建表.sql 的基线结构，缺 up_upstream_key 表与
up_upstream.enabled/models/smart_retry/groups 四列，启动时会直接崩。
"""

import os
import sqlite3
import sys

# 与 app/core/database.py 保持同一口径：环境变量优先
DB_PATH = os.environ.get("SMART_ROUTER_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "smart_router.db"
)
SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")

# 按依赖顺序：基线 -> 种子 -> 增量 01~05 -> 06 用量 -> 增量 06~08
SQL_FILES = (
    "01_建表.sql",
    "02_init_data.sql",
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
    "increment/11_增量_20261019_请求详情可观测性.sql",
    "increment/12_增量_20261021_请求过滤引擎.sql",
)


def drop_all(conn: sqlite3.Connection) -> None:
    """删除所有业务表（幂等重建）"""
    tables = [
        # 基线
        "rule_candidate", "rule_rule", "api_api_key",
        "up_upstream", "pt_pointer", "agg_aggregated_name", "sys_setting",
        # 增量
        "up_upstream_key", "log_usage", "agg_model_group",
        "agg_probe_config", "agg_probe_template", "agg_unified", "log_usage_detail",
        "filter_rule",
    ]
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


def run_sql_file(conn: sqlite3.Connection, filename: str) -> None:
    path = os.path.join(SQL_DIR, filename.replace("/", os.sep))
    if not os.path.exists(path):
        print(f"[seed] 跳过（文件不存在）: {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    print(f"[seed] 已执行: {filename}")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        print(f"[seed] 初始化数据库: {DB_PATH}")
        drop_all(conn)
        for filename in SQL_FILES:
            run_sql_file(conn, filename)
        print("[seed] 初始化完成 ✅")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

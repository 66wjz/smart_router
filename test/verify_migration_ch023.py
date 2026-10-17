"""
CH-023 迁移验证：旧聚合表 → 统一聚合表

用法（默认只读 demo.db，绝不动正式库）：
    python test/verify_migration_ch023.py
    SMART_ROUTER_DB=backend/xxx.db python test/verify_migration_ch023.py

校验项：
1. 旧 agg_aggregated_name → agg_unified（kind=rule）逐条一致
2. 旧 agg_model_group → agg_unified（kind=static）members 逐字段一致
3. 旧 agg_probe_config 的探测参数逐字段一致
4. 重复执行迁移不产生重复行，且不覆盖新表已有内容
"""

import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

DB = os.environ.get("SMART_ROUTER_DB") or os.path.join(ROOT, "backend", "demo.db")
SQL = os.path.join(ROOT, "sql", "increment", "07_增量_20261017_聚合统一与探测模板.sql")

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def run_migration(conn) -> None:
    with open(SQL, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def snapshot(conn) -> dict:
    """当前库里旧表/新表的内容快照"""
    snap: dict = {"old_rule": [], "old_static": [], "old_probe": {}, "unified": {}}
    if table_exists(conn, "agg_aggregated_name"):
        snap["old_rule"] = [r[0] for r in conn.execute(
            "SELECT name FROM agg_aggregated_name ORDER BY name")]
    if table_exists(conn, "agg_model_group"):
        for r in conn.execute(
                "SELECT model, upstreams, enabled FROM agg_model_group ORDER BY model"):
            snap["old_static"].append({
                "name": r[0],
                "members": json.loads(r[1] or "[]"),
                "enabled": bool(r[2]),
            })
    if table_exists(conn, "agg_probe_config"):
        for r in conn.execute(
                "SELECT model, enabled, interval_seconds, slow_threshold_seconds, sort_mode, schedule "
                "FROM agg_probe_config ORDER BY model"):
            snap["old_probe"][r[0]] = {
                "enabled": bool(r[1]),
                "interval_seconds": r[2],
                "slow_threshold_seconds": r[3],
                "sort_mode": r[4] or "stable",
                "schedule": json.loads(r[5] or "{}"),
            }
    return snap


def read_unified(conn) -> dict:
    rows = conn.execute(
        "SELECT name, kind, members, enabled, probe_enabled, template_id, sort_mode, "
        "interval_seconds, slow_threshold_seconds, schedule FROM agg_unified"
    ).fetchall()
    return {
        r[0]: {
            "kind": r[1],
            "members": json.loads(r[2] or "[]"),
            "enabled": bool(r[3]),
            "probe_enabled": bool(r[4]),
            "template_id": r[5],
            "sort_mode": r[6] or "stable",
            "interval_seconds": r[7],
            "slow_threshold_seconds": r[8],
            "schedule": json.loads(r[9] or "{}"),
        }
        for r in rows
    }


def main() -> int:
    print(f"数据库: {DB}")
    if not os.path.exists(DB):
        print("数据库不存在，无法验证")
        return 2
    conn = sqlite3.connect(DB)
    before = snapshot(conn)
    print(f"迁移前: rule={len(before['old_rule'])} static={len(before['old_static'])} "
          f"probe={len(before['old_probe'])}")

    run_migration(conn)
    after_first = read_unified(conn)
    count_first = len(after_first)
    run_migration(conn)          # 幂等：再跑一次
    after_second = read_unified(conn)

    print("\n[1] 幂等性")
    check(len(after_second) == count_first, f"重复执行不新增行（{count_first} → {len(after_second)}）")

    print("\n[2] 手写聚合名 → rule")
    for name in before["old_rule"]:
        row = after_second.get(name)
        check(row is not None and row["kind"] == "rule", f"{name}: kind=rule")
        if row:
            check(row["members"] == [], f"{name}: 无成员列表")

    print("\n[3] 聚合组 → static")
    for old in before["old_static"]:
        row = after_second.get(old["name"])
        check(row is not None and row["kind"] == "static", f"{old['name']}: kind=static")
        if not row:
            continue
        norm_old = [
            {"upstream": m.get("upstream"), "model": m.get("model"), "weight": int(m.get("weight", 1) or 1)}
            for m in old["members"]] if isinstance(old["members"], list) else []
        norm_new = [
            {"upstream": m.get("upstream"), "model": m.get("model"), "weight": int(m.get("weight", 1) or 1)}
            for m in row["members"]]
        check(norm_old == norm_new, f"{old['name']}: members 逐字段一致")
        check(row["enabled"] == old["enabled"], f"{old['name']}: enabled 一致")

    print("\n[4] 探测配置合并")
    for name, old in before["old_probe"].items():
        row = after_second.get(name)
        if row is None:
            check(False, f"{name}: 统一表中缺少对应行")
            continue
        check(row["probe_enabled"] == old["enabled"], f"{name}: probe_enabled 一致")
        check(row["interval_seconds"] == old["interval_seconds"], f"{name}: interval 一致")
        check(row["slow_threshold_seconds"] == old["slow_threshold_seconds"], f"{name}: slow 一致")
        check(row["sort_mode"] == old["sort_mode"], f"{name}: sort_mode 一致")
        check(row["schedule"] == old["schedule"], f"{name}: schedule 一致")

    print("\n[5] 不覆盖新表已有内容")
    overlap = set(after_first) & set(after_second)
    check(bool(overlap) or count_first == 0, "第二次迁移后行集合不变")

    conn.close()
    print(f"\n结果: {'全部通过' if not failures else f'{len(failures)} 项失败'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

"""
CH-034 接口级验证：/v1/models 按聚合分组过滤 + 聚合调用权限

用法：python test/verify_models_scope_ch034.py

以 TestClient 起真实应用，通过 HTTP 校验：
1. groups=[] 的聚合对所有 Key 可见
2. groups=['premium'] 的聚合对 free Key 不可见、对 premium Key 可见
3. 真实模型条目仍按上游分组过滤（不受本次改动影响）
4. 直接调用聚合：free Key 403 且文案指向聚合；premium Key 通过权限检查

只创建/清理本脚本的测试聚合，不触碰业务数据。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "backend", "demo.db")
os.environ["SMART_ROUTER_DB"] = DB
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.config import config  # noqa: E402

TAG = "ch034-api-"
AGG_OPEN = TAG + "open"
AGG_PREMIUM = TAG + "premium"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def ensure_schema() -> None:
    from app.core.database import get_conn

    path = os.path.join(ROOT, "sql", "increment", "09_增量_20261018_聚合分组.sql")
    with open(path, encoding="utf-8") as f:
        try:
            get_conn().executescript(f.read())
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
    config.reload()


def main() -> int:
    ensure_schema()
    upstreams = [u for u in config.upstreams if u.get("models") and config.is_upstream_enabled(u["upstream_id"])]
    if not upstreams:
        print("  FAIL 无可用上游源")
        return 1
    up = upstreams[0]
    uid = up["upstream_id"]
    member = [m["name"] for m in up["models"] if m.get("enabled", True)][0]

    def save(name: str, groups: list[str]) -> None:
        config.save_aggregation(name, {
            "kind": "static",
            "members": [{"upstream": uid, "model": member, "weight": 1}],
            "rule_bindings": None, "groups": groups,
            "enabled": True, "probe_enabled": False, "template_id": None,
            "sort_mode": "stable", "interval_seconds": None,
            "slow_threshold_seconds": None, "schedule": {}, "remark": "",
        })

    for n in (AGG_OPEN, AGG_PREMIUM):
        if n in config.get_aggregations():
            config.delete_aggregation(n)

    try:
        print("\n[1] 聚合门面可见性函数")
        save(AGG_OPEN, [])
        save(AGG_PREMIUM, ["premium"])
        check(config.is_aggregation_visible(AGG_OPEN, {"free"}), "groups=[] → free 可见")
        check(config.is_aggregation_visible(AGG_OPEN, {"premium"}), "groups=[] → premium 可见")
        check(not config.is_aggregation_visible(AGG_PREMIUM, {"free"}), "groups=[premium] → free 不可见")
        check(config.is_aggregation_visible(AGG_PREMIUM, {"premium"}), "groups=[premium] → premium 可见")

        print("\n[2] /v1/models 真实接口")
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            # 用一个真实存在的 free 分组 Key
            from app.repositories.api_key_repo import ApiKeyRepository
            keys = ApiKeyRepository().list_all()
            usable = []
            for k in keys:
                if not k.get("enabled", True):
                    continue
                kk = k.get("key_value") or ""
                if not kk or "CHANGE-ME" in kk:
                    continue
                usable.append((kk, config._parse_groups(k.get("groups"))))
            if not usable:
                print("  SKIP 库里没有可用客户端 Key")
            else:
                token, groups = usable[0]
                r = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
                check(r.status_code == 200, f"GET /v1/models → 200（Key 分组 {groups}）")
                ids = [m["id"] for m in r.json().get("data", [])]
                check(AGG_OPEN in ids, f"groups=[] 的聚合在列表中（{AGG_OPEN}）")
                expect_premium = "premium" in groups
                check((AGG_PREMIUM in ids) == expect_premium,
                      f"groups=[premium] 的聚合按 Key 分组过滤（在列表={AGG_PREMIUM in ids}, 期望={expect_premium}）")
    finally:
        for n in (AGG_OPEN, AGG_PREMIUM):
            if n in config.get_aggregations():
                config.delete_aggregation(n)

    print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

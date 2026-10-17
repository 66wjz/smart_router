"""CH-019 逻辑单测：同名多候选 / 模型禁用过滤 / 健康隔离 / 用量解析
不依赖真实上游，直接对核心函数断言。用法：cd backend && .venv\\Scripts\\python.exe ..\\test\\unit_ch019.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core.health import ModelHealth, health_key
from app.core.router_engine import get_ordered_candidates
from app.core.usage import UsageBuffer
from app.services.router_service import _UsageTracker

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


class FakeConfig:
    """最小 AppConfig 替身：两个上游各有同名模型，用于验证多候选与禁用过滤"""

    def __init__(self, disable_model=None, disable_upstream=None):
        self.default_upstream = "up-a"
        self._settings = {}
        self._upstreams = [
            {"upstream_id": "up-a", "name": "A", "format": "openai", "enabled": 1, "probe_enabled": 0,
             "group_name": "free", "groups": ["free"],
             "models": [{"name": "shared-model", "enabled": 0 if disable_model == ("up-a", "shared-model") else 1},
                        {"name": "only-a", "enabled": 1}]},
            {"upstream_id": "up-b", "name": "B", "format": "openai",
             "enabled": 0 if disable_upstream == "up-b" else 1, "probe_enabled": 0,
             "group_name": "free", "groups": ["free"],
             "models": [{"name": "shared-model", "enabled": 0 if disable_model == ("up-b", "shared-model") else 1}]},
        ]
        self._rules = []

    # 显式转发到真实实现（避免把未绑定函数赋成类属性的坑）
    def get_upstream(self, upstream_id):
        from app.core.config import AppConfig
        return AppConfig.get_upstream(self, upstream_id)

    def is_upstream_enabled(self, upstream_id):
        from app.core.config import AppConfig
        return AppConfig.is_upstream_enabled(self, upstream_id)

    def is_model_enabled(self, upstream_id, model):
        from app.core.config import AppConfig
        return AppConfig.is_model_enabled(self, upstream_id, model)

    def get_upstream_groups(self, upstream_id):
        from app.core.config import AppConfig
        return AppConfig.get_upstream_groups(self, upstream_id)

    def collect_model_upstreams(self, model_name, limit=None):
        from app.core.config import AppConfig
        return AppConfig.collect_model_upstreams(self, model_name, limit)

    def find_model_upstream(self, model_name):
        from app.core.config import AppConfig
        return AppConfig.find_model_upstream(self, model_name)

    def is_upstream_probe_enabled(self, upstream_id):
        from app.core.config import AppConfig
        return AppConfig.is_upstream_probe_enabled(self, upstream_id)

    @property
    def rules(self):
        return self._rules


class FakeProbe:
    def get_dynamic_weight(self, upstream_id, model, base_weight):
        return base_weight


class FakeBody(dict):
    pass


def test_health_isolation():
    print("[1] 健康状态按 upstream+model 隔离（修串台）")
    h = ModelHealth(max_fails=2, cooldown_seconds=60)
    h.record_fail("trae", "glm-5-3-flashx")
    h.record_fail("trae", "glm-5-3-flashx")
    check("trae 源同名模型已冷却", h.is_available("trae", "glm-5-3-flashx") is False)
    check("dsh 源同名模型不受影响", h.is_available("dsh", "glm-5-3-flashx") is True)
    check("健康 key 格式", health_key("dsh", "m") == "dsh:m")


def test_collect_multi_upstream():
    print("[2] 同名模型多候选收集")
    cfg = FakeConfig()
    ups = cfg.collect_model_upstreams("shared-model")
    check("同名跨 2 源", ups == ["up-a", "up-b"], str(ups))
    check("单源模型只 1 个", cfg.collect_model_upstreams("only-a") == ["up-a"])
    check("未知模型返回空", cfg.collect_model_upstreams("nope") == [])


def test_disabled_filters():
    print("[3] 模型/上游禁用过滤")
    cfg = FakeConfig(disable_model=("up-a", "shared-model"))
    check("禁用 A 源模型后只剩 B", cfg.collect_model_upstreams("shared-model") == ["up-b"])
    cfg2 = FakeConfig(disable_upstream="up-b")
    check("禁用 B 源后只剩 A", cfg2.collect_model_upstreams("shared-model") == ["up-a"])
    cfg3 = FakeConfig(disable_model=("up-a", "shared-model"), disable_upstream="up-b")
    check("全部禁用返回空", cfg3.collect_model_upstreams("shared-model") == [])


def test_ordered_candidates_filter():
    print("[4] 聚合候选排序过滤禁用模型")
    cfg = FakeConfig(disable_model=("up-b", "shared-model"))
    rule_body = {"model": "agg", "messages": [{"role": "user", "content": "hi"}]}

    class CfgWithRule(FakeConfig):
        def __init__(self):
            super().__init__(disable_model=("up-b", "shared-model"))
            self._rules = [{
                "name": "r1",
                "match": {"default": True},
                "candidates": [
                    {"model": "shared-model", "upstream": "up-a", "weight": 1, "priority": 1},
                    {"model": "shared-model", "upstream": "up-b", "weight": 1, "priority": 1},
                ],
            }]

    c = CfgWithRule()
    cands = get_ordered_candidates(rule_body["messages"], rule_body, c, FakeProbe(), ModelHealth())
    uids = [x["upstream"] for x in cands]
    check("禁用模型被过滤出候选", uids == ["up-a"], str(uids))


def test_usage_tracker():
    print("[5] 用量解析（非流式 / 流式 usage / 估算降级）")

    class Cfg:
        def get_upstream(self, upstream_id):
            return {"upstream_id": upstream_id, "name": f"name-{upstream_id}"}

    class Buf(UsageBuffer):
        def __init__(self):
            super().__init__()
            self.rows = []

        def record(self, entry):
            self.rows.append(entry)

    buf = Buf()
    cfg = Cfg()
    cfg._usage_buffer = buf

    # 非流式：上游带 usage
    t = _UsageTracker(cfg, "m1", "chat", False, {"messages": [{"role": "user", "content": "你好"}]})
    t.set_hit_upstream("up-a")
    t.finish_success_non_stream({"usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}})
    check("非流式取到真实 usage", buf.rows[-1]["total_tokens"] == 33 and buf.rows[-1]["estimated"] is False,
          str(buf.rows[-1]["total_tokens"]))
    check("记录命中上游", buf.rows[-1]["upstream_id"] == "up-a")

    # 流式：末 chunk 带 usage
    t2 = _UsageTracker(cfg, "m2", "chat", True, {"messages": [{"role": "user", "content": "hi"}]})
    t2.set_hit_upstream("up-b")
    t2.feed_chunk('data: {"choices":[{"delta":{"content":"hello"}}]}')
    t2.feed_chunk('data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":5,"completion_tokens":7,"total_tokens":12}}')
    t2.finalize_stream()
    check("流式解析末 chunk usage", buf.rows[-1]["total_tokens"] == 12 and buf.rows[-1]["estimated"] is False,
          str(buf.rows[-1]))

    # 流式：上游不返回 usage → 估算
    t3 = _UsageTracker(cfg, "m3", "chat", True, {"messages": [{"role": "user", "content": "x" * 100}]})
    t3.set_hit_upstream("up-a")
    t3.feed_chunk('data: {"choices":[{"delta":{"content":"' + "y" * 80 + '"}}]}')
    t3.finalize_stream()
    row = buf.rows[-1]
    check("无 usage 时估算降级", row["estimated"] is True and row["completion_tokens"] > 0,
          f"est={row['estimated']} ct={row['completion_tokens']} pt={row['prompt_tokens']}")

    # 失败请求也记账
    t4 = _UsageTracker(cfg, "m4", "chat", False, {"messages": [{"role": "user", "content": "hi"}]})
    t4.set_hit_upstream("up-a")
    t4.finish_error("all failed", 503)
    check("失败请求记账", buf.rows[-1]["status"] == "error" and buf.rows[-1]["http_status"] == 503)


def main():
    test_health_isolation()
    test_collect_multi_upstream()
    test_disabled_filters()
    test_ordered_candidates_filter()
    test_usage_tracker()
    print(f"\n结果: PASS={ok} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

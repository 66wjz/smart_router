"""
延迟探测模块 - 定期给探测单元发请求，记录实时延迟

CH-019：探测粒度从纯模型名改为 (upstream_id, model) 二元组，同名模型跨上游源全探测
CH-021：探测单元由「全局去重计划」统一决定；按单元到期调度（支持每组独立间隔/时段）；
        并发限流；探测失败默认不计入 Key 冷却
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.health import ModelHealth

log = logging.getLogger("router")

# 同一单元最小调度粒度：避免短间隔把循环压满
TICK_SECONDS = 1.0


class LatencyProbe:
    """按去重后的探测单元集合，定时探测各 (上游源, 模型) 的延迟"""

    def __init__(self, app_config: "AppConfig"):
        self.config = app_config
        self.data: dict[str, dict] = {}      # key = f"{upstream_id}:{model}"
        self._next_due: dict[str, float] = {}
        self._running = False
        self._init_models()

    @staticmethod
    def _key(upstream_id: str, model: str) -> str:
        return f"{upstream_id}:{model}"

    @staticmethod
    def _split_key(key: str) -> tuple[str, str]:
        """拆出 (upstream_id, model)；模型名可能含冒号，只切第一个冒号"""
        uid, _, model = key.partition(":")
        return uid, model

    # ------------------------------------------------------------
    # 探测计划同步
    # ------------------------------------------------------------

    def _init_models(self) -> dict[str, dict]:
        """按当前探测计划增删状态项；返回计划本身"""
        plan = self.config.collect_probe_plan()
        for key, item in plan.items():
            entry = self.data.get(key)
            if entry is None:
                self.data[key] = {
                    "latency": None,
                    "status": "unknown",
                    "last_check": 0,
                    "error": None,
                    "interval": item["interval"],
                }
            else:
                entry["interval"] = item["interval"]
        for key in list(self.data.keys()):
            if key not in plan:
                del self.data[key]
                self._next_due.pop(key, None)
        return plan

    # ------------------------------------------------------------
    # 单单元探测
    # ------------------------------------------------------------

    async def probe_one(self, client: httpx.AsyncClient, key: str) -> dict:
        """探测单个 (upstream, model)（Key 池选 Key；401/403/429/超时/异常换下一个 Key，全部 Key 失败才判 down）"""
        probe_cfg = self.config.probe_config
        timeout = probe_cfg.get("timeout_seconds", 35)
        text = probe_cfg.get("request_text", "Hi")
        max_tokens = probe_cfg.get("max_tokens", 3)
        count_key_failures = bool(probe_cfg.get("count_key_failures", False))

        upstream_id, model = self._split_key(key)
        upstream = self.config.get_upstream(upstream_id) or {}
        base_url = upstream.get("base_url", "").rstrip("/")
        fmt = upstream.get("format", "openai")
        keys = self.config.get_upstream_keys(upstream_id)

        if not base_url:
            return {"latency": None, "status": "down", "error": "no_upstream"}
        if not keys:
            return {"latency": None, "status": "down", "error": "no_key"}

        last_error = None
        for _ in range(len(keys)):
            api_key = self.config.key_pool.pick(upstream_id, keys)
            if not api_key:
                break

            body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens}
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            if fmt == "anthropic":
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
                if "Authorization" in headers:
                    del headers["Authorization"]
                url = f"{base_url}/v1/messages"
            else:
                url = f"{base_url}/v1/chat/completions"

            try:
                t0 = time.time()
                resp = await client.post(url, json=body, headers=headers, timeout=timeout)
                elapsed = round(time.time() - t0, 2)
                if resp.status_code == 200:
                    self.config.key_pool.record_success(upstream_id, api_key)
                    down_threshold = probe_cfg.get("down_threshold_seconds", 30)
                    if elapsed >= down_threshold:
                        return {"latency": elapsed, "status": "down", "error": "too_slow"}
                    return {"latency": elapsed, "status": "ok", "error": None}
                if resp.status_code in (401, 403, 429):
                    # CH-021：探测失败默认不计入 Key 冷却（避免探测把唯一 Key 打进冷却，害死真实请求）
                    if count_key_failures:
                        self.config.key_pool.record_fail(upstream_id, api_key)
                    last_error = f"HTTP {resp.status_code}"
                    continue
                last_error = f"HTTP {resp.status_code}"
                break
            except httpx.TimeoutException:
                if count_key_failures:
                    self.config.key_pool.record_fail(upstream_id, api_key)
                last_error = "timeout"
                continue
            except Exception as e:
                if count_key_failures:
                    self.config.key_pool.record_fail(upstream_id, api_key)
                last_error = str(e)[:100]
                continue

        if probe_cfg.get("error_as_down", True):
            return {"latency": None, "status": "down", "error": last_error or "no_available_key"}
        return {"latency": None, "status": "unknown", "error": last_error or "no_available_key"}

    # ------------------------------------------------------------
    # 批量探测
    # ------------------------------------------------------------

    def _concurrency(self) -> int:
        try:
            return max(1, int(self.config.probe_config.get("max_concurrency", 5) or 5))
        except (TypeError, ValueError):
            return 5

    async def probe_keys(self, client: httpx.AsyncClient, keys: list[str]) -> None:
        """并发探测指定单元（信号量限流），结果写回 self.data"""
        if not keys:
            return
        sem = asyncio.Semaphore(self._concurrency())

        async def run(k: str) -> tuple[str, dict]:
            async with sem:
                try:
                    return k, await self.probe_one(client, k)
                except Exception as e:  # 单单元异常不影响整轮
                    return k, {"latency": None, "status": "unknown", "error": str(e)[:100]}

        results = await asyncio.gather(*(run(k) for k in keys))
        now = time.time()
        for key, result in results:
            self._apply_result(key, result, now)

    def _apply_result(self, key: str, result: dict, now: float) -> None:
        old = self.data.get(key, {})
        self.data[key] = {
            "latency": result["latency"],
            "status": result["status"],
            "last_check": now,
            "error": result["error"],
            "interval": old.get("interval", self.config.probe_config.get("interval_seconds", 120)),
        }
        old_status = old.get("status", "unknown")
        new_status = result["status"]
        new_latency = result["latency"]
        old_latency = old.get("latency")

        if old_status != new_status:
            latency_str = f"{new_latency}s" if new_latency else "N/A"
            log.warning(f"[探测] {key}: {old_status} → {new_status} (延迟={latency_str})")
        elif new_latency and old_latency and abs(new_latency - old_latency) / max(old_latency, 0.1) > 0.5:
            log.info(f"[探测] {key}: 延迟变化 {old_latency}s → {new_latency}s")

    async def probe_all(self, client: httpx.AsyncClient) -> None:
        """立即探测全部单元（手动/兼容入口，忽略时段限制）"""
        self._init_models()
        keys = list(self.data.keys())
        now = time.time()
        await self.probe_keys(client, keys)
        for key in keys:
            self._next_due[key] = now + self._interval_of(key)

    def _interval_of(self, key: str) -> int:
        item = self.data.get(key) or {}
        try:
            return max(5, int(item.get("interval") or self.config.probe_config.get("interval_seconds", 120)))
        except (TypeError, ValueError):
            return 120

    # ------------------------------------------------------------
    # 调度循环
    # ------------------------------------------------------------

    async def run_loop(self, client: httpx.AsyncClient) -> None:
        """按单元到期调度：每个单元按自己的间隔探测，支持组级不同节奏与探测时段"""
        self._running = True
        plan = self._init_models()
        if not plan:
            log.info("[探测] 启动延迟探测，当前无探测单元")
        else:
            intervals = sorted({p["interval"] for p in plan.values()})
            log.info(f"[探测] 启动延迟探测，{len(plan)} 个去重单元，间隔 {intervals}")

        # 启动时立刻探一轮（不等待首个间隔）
        await self._tick(client, initial=True)

        while self._running:
            await asyncio.sleep(TICK_SECONDS)
            try:
                await self._tick(client, initial=False)
            except Exception as e:
                log.error(f"[探测] 调度异常: {e}")

    async def _tick(self, client: httpx.AsyncClient, initial: bool = False) -> None:
        plan = self._init_models()
        now = time.time()
        due: list[str] = []

        for key, item in plan.items():
            if not self.config.probe_plan_active(item):
                # 时段外：不作废已有数据，只在面板标记陈旧
                self._next_due[key] = now + 60
                continue
            next_at = self._next_due.get(key)
            if next_at is None or initial or now >= next_at:
                due.append(key)

        if not due:
            return

        await self.probe_keys(client, due)
        after = time.time()
        for key in due:
            self._next_due[key] = after + self._interval_of(key)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------
    # 排序 / 面板
    # ------------------------------------------------------------

    def get_dynamic_weight(self, upstream_id: str, model: str, base_weight: float) -> float:
        """
        根据实时延迟计算动态权重（CH-019：按 upstream+model 查）。
        公式: dynamic_weight = base_weight * (base_latency / model_latency)²
        """
        info = self.data.get(self._key(upstream_id, model))
        if not info:
            return base_weight
        if info["status"] == "down":
            return 0
        if info["latency"] is None:
            return base_weight

        base_lat = self.config.probe_config.get("base_latency", 0.5)
        model_lat = info["latency"]
        slow_threshold = self.config.probe_config.get("slow_threshold_seconds", 10)
        if model_lat <= 0:
            return base_weight
        if model_lat > slow_threshold:
            return 0
        ratio = (base_lat / model_lat) ** 2
        dynamic = base_weight * ratio
        dynamic = max(0.1, min(dynamic, base_weight * 3))
        return round(dynamic, 2)

    def sort_group_candidates(self, candidates: list[dict], group_name: str,
                              health: "ModelHealth | None" = None) -> list[dict]:
        """聚合候选排序（CH-021）

        T0 正常（ok 且未超慢阈值、未冷却）→ T1 偏慢/未知 → T2 不可用/冷却。
        stable：层内保持配置顺序；latency：层内按延迟升序（无数据最后）。

        兜底：全部候选都落入 T2 时，直接返回配置顺序——绝不让"全 down"变成无候选 503。
        """
        if len(candidates) <= 1:
            return list(candidates)

        settings = self.config.group_probe_settings(group_name)
        slow = settings.get("slow_threshold_seconds") or self.config.probe_config.get(
            "slow_threshold_seconds", 10)
        mode = settings.get("sort_mode") or "stable"

        tiers: dict[int, list[dict]] = {0: [], 1: [], 2: []}
        for cand in candidates:
            uid = cand.get("upstream", "")
            model = cand.get("model", "")
            info = self.data.get(self._key(uid, model)) or {}
            status = info.get("status", "unknown")
            latency = info.get("latency")
            cooling = bool(health and not health.is_available(uid, model))

            if cooling or status == "down":
                tier = 2
            elif status == "ok" and latency is not None and latency <= slow:
                tier = 0
            else:
                tier = 1
            tiers[tier].append({**cand, "_latency": latency})

        if not tiers[0] and not tiers[1]:
            return list(candidates)  # 全不可用 → 兜底原顺序

        def within(items: list[dict]) -> list[dict]:
            if mode != "latency":
                return items
            return sorted(items, key=lambda c: (c["_latency"] is None, c["_latency"] or 0))

        ordered = within(tiers[0]) + within(tiers[1]) + within(tiers[2])
        return [{k: v for k, v in c.items() if k != "_latency"} for c in ordered]

    def get_panel(self) -> dict:
        """获取延迟面板数据（key 为 upstream_id:model）"""
        now = time.time()
        result = {}
        for k, d in self.data.items():
            interval = d.get("interval") or 120
            last = d.get("last_check") or 0
            result[k] = {
                "latency": f"{d['latency']}s" if d["latency"] is not None else "N/A",
                "status": d["status"],
                "error": d["error"],
                "interval": interval,
                "last_check": last,
                "stale": bool(last and now - last > interval * 3),
            }
        return result

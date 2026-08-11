"""
延迟探测模块 - 定期给所有候选模型发探测请求，记录实时延迟
从 v4 core/probe.py 迁移，import 路径改为 app 包结构
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.config import AppConfig

log = logging.getLogger("router")


class LatencyProbe:
    """定期探测所有候选模型的延迟"""

    def __init__(self, app_config: "AppConfig"):
        self.config = app_config
        self.data: dict[str, dict] = {}
        self._running = False
        self._init_models()

    def _init_models(self) -> None:
        """初始化所有候选模型的状态（跳过 probe_enabled=false 或已禁用上游的模型）"""
        all_models = self.config.get_all_models()
        probeable_models = set()
        for m in all_models:
            upstream_id = self.config.find_model_upstream(m)
            if self.config.is_upstream_probe_enabled(upstream_id) and self.config.is_upstream_enabled(upstream_id):
                probeable_models.add(m)

        for m in probeable_models:
            if m not in self.data:
                self.data[m] = {"latency": None, "status": "unknown", "last_check": 0, "error": None}
        for m in list(self.data.keys()):
            if m not in probeable_models:
                del self.data[m]

    async def probe_one(self, client: httpx.AsyncClient, model: str) -> dict:
        """探测单个模型（Key 池选 Key；401/403/429/超时/异常换下一个 Key，全部 Key 失败才判 down）"""
        probe_cfg = self.config.probe_config
        timeout = probe_cfg.get("timeout_seconds", 35)
        text = probe_cfg.get("request_text", "Hi")
        max_tokens = probe_cfg.get("max_tokens", 3)

        upstream_id = None
        for rule in self.config.rules:
            for c in rule.get("candidates", []):
                if c.get("model") == model:
                    upstream_id = c.get("upstream")
                    break
            if upstream_id:
                break
        if not upstream_id:
            upstream_id = self.config.default_upstream
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
                    self.config.key_pool.record_fail(upstream_id, api_key)
                    last_error = f"HTTP {resp.status_code}"
                    continue
                last_error = f"HTTP {resp.status_code}"
                break
            except httpx.TimeoutException:
                self.config.key_pool.record_fail(upstream_id, api_key)
                last_error = "timeout"
                continue
            except Exception as e:
                self.config.key_pool.record_fail(upstream_id, api_key)
                last_error = str(e)[:100]
                continue

        if probe_cfg.get("error_as_down", True):
            return {"latency": None, "status": "down", "error": last_error or "no_available_key"}
        return {"latency": None, "status": "unknown", "error": last_error or "no_available_key"}

    async def probe_all(self, client: httpx.AsyncClient) -> None:
        """并行探测所有模型"""
        if not self.config.probe_config.get("enabled", True):
            return
        self._init_models()
        tasks = {m: self.probe_one(client, m) for m in self.data}
        results = {}
        for m, coro in tasks.items():
            results[m] = await coro

        now = time.time()
        for model, result in results.items():
            old = self.data.get(model, {})
            self.data[model] = {
                "latency": result["latency"],
                "status": result["status"],
                "last_check": now,
                "error": result["error"],
            }
            old_status = old.get("status", "unknown")
            new_status = result["status"]
            new_latency = result["latency"]
            old_latency = old.get("latency")

            if old_status != new_status:
                latency_str = f"{new_latency}s" if new_latency else "N/A"
                log.warning(f"[探测] {model}: {old_status} → {new_status} (延迟={latency_str})")
            elif new_latency and old_latency and abs(new_latency - old_latency) / max(old_latency, 0.1) > 0.5:
                log.info(f"[探测] {model}: 延迟变化 {old_latency}s → {new_latency}s")

    async def run_loop(self, client: httpx.AsyncClient) -> None:
        """后台循环探测"""
        interval = self.config.probe_config.get("interval_seconds", 120)
        self._running = True
        self._init_models()
        log.info(f"[探测] 启动延迟探测，每 {interval}s 探测 {len(self.data)} 个模型")
        await self.probe_all(client)
        while self._running:
            await asyncio.sleep(interval)
            try:
                await self.probe_all(client)
            except Exception as e:
                log.error(f"[探测] 异常: {e}")

    def stop(self) -> None:
        self._running = False

    def get_dynamic_weight(self, model: str, base_weight: float) -> float:
        """
        根据实时延迟计算动态权重。
        公式: dynamic_weight = base_weight * (base_latency / model_latency)²
        """
        info = self.data.get(model)
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

    def get_panel(self) -> dict:
        """获取延迟面板数据"""
        return {
            m: {
                "latency": f"{d['latency']}s" if d["latency"] is not None else "N/A",
                "status": d["status"],
                "error": d["error"],
            }
            for m, d in self.data.items()
        }

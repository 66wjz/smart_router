"""
Key 池模块 - 上游源多 API Key 的选择与健康跟踪
- 轮询选择：同一上游源的多个 Key 分摊流量
- Key 级健康：401/403/429 连续失败进入冷却，成功清零，冷却后自动恢复
- 运行时内存状态，不落库（库中仅存 api_key + enabled）
"""

import logging
import threading
import time

from app.core.affinity import current_preferred_key, current_used_key

log = logging.getLogger("router")


class KeyPool:
    def __init__(self, max_fails: int = 3, cooldown_seconds: int = 120):
        self.max_fails = max_fails
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.RLock()
        self._rr: dict[str, int] = {}            # upstream_id -> 轮询下标
        self._fails: dict[str, dict[str, int]] = {}  # upstream_id -> {key: 连续失败数}
        self._cooldown_until: dict[str, dict[str, float]] = {}  # upstream_id -> {key: 冷却截止}

    def update_config(self, max_fails: int, cooldown_seconds: int) -> None:
        with self._lock:
            self.max_fails = max_fails
            self.cooldown_seconds = cooldown_seconds

    def reset(self, upstream_id: str) -> None:
        """上游 Key 池变更/热重载时重置该上游的运行时状态"""
        with self._lock:
            self._rr.pop(upstream_id, None)
            self._fails.pop(upstream_id, None)
            self._cooldown_until.pop(upstream_id, None)

    def _is_key_available(self, upstream_id: str, key: str) -> bool:
        until = self._cooldown_until.get(upstream_id, {}).get(key, 0)
        if time.time() < until:
            return False
        return True

    def pick(self, upstream_id: str, keys: list[str]) -> str | None:
        """选择 Key：会话亲和优先用上次成功的 Key，否则轮询"""
        if not keys:
            return None
        preferred = current_preferred_key.get()
        with self._lock:
            if preferred and preferred in keys and self._is_key_available(upstream_id, preferred):
                current_used_key.set(preferred)
                return preferred
            idx = self._rr.get(upstream_id, -1)
            for _ in range(len(keys)):
                idx = (idx + 1) % len(keys)
                key = keys[idx]
                if self._is_key_available(upstream_id, key):
                    self._rr[upstream_id] = idx
                    current_used_key.set(key)
                    return key
        return None

    def record_fail(self, upstream_id: str, key: str) -> None:
        with self._lock:
            fails = self._fails.setdefault(upstream_id, {})
            n = fails.get(key, 0) + 1
            fails[key] = n
            if n >= self.max_fails:
                self._cooldown_until.setdefault(upstream_id, {})[key] = time.time() + self.cooldown_seconds
                log.warning(f"Key 池 [{upstream_id}] Key 连续失败 {n} 次，冷却 {self.cooldown_seconds}s")

    def record_success(self, upstream_id: str, key: str) -> None:
        with self._lock:
            fails = self._fails.get(upstream_id)
            if fails and key in fails:
                fails.pop(key, None)

    def get_status(self) -> dict:
        """健康快照（供仪表盘/调试）"""
        with self._lock:
            return {
                "fails": {u: dict(f) for u, f in self._fails.items()},
                "cooldown": {
                    u: {k: max(0, int(v - time.time())) for k, v in cu.items()}
                    for u, cu in self._cooldown_until.items()
                },
            }

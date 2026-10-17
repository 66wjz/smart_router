"""
故障转移模块 - 模型健康状态跟踪
CH-019：健康 key 从纯模型名改为 upstream_id:model，修复同名模型跨上游源串台
"""

import logging
import time

log = logging.getLogger("router")


def health_key(upstream_id: str, model: str) -> str:
    """健康状态的唯一键：upstream_id:model"""
    return f"{upstream_id}:{model}"


class ModelHealth:
    """模型健康状态管理（按 上游源+模型 隔离）"""

    def __init__(self, max_fails: int = 3, cooldown_seconds: int = 120):
        self.max_fails = max_fails
        self.cooldown_seconds = cooldown_seconds
        self.fails: dict[str, int] = {}
        self.cooldown_until: dict[str, float] = {}

    def update_config(self, max_fails: int, cooldown_seconds: int) -> None:
        self.max_fails = max_fails
        self.cooldown_seconds = cooldown_seconds

    def record_fail(self, upstream_id: str, model: str) -> None:
        """记录一次失败，达到阈值则进入冷却（仅影响该上游源的该模型）"""
        key = health_key(upstream_id, model)
        self.fails[key] = self.fails.get(key, 0) + 1
        if self.fails[key] >= self.max_fails:
            self.cooldown_until[key] = time.time() + self.cooldown_seconds
            log.warning(f"模型 {model}@{upstream_id} 连续失败 {self.fails[key]} 次，冷却 {self.cooldown_seconds}s")

    def record_success(self, upstream_id: str, model: str) -> None:
        """记录成功，清除失败计数"""
        self.fails.pop(health_key(upstream_id, model), None)

    def is_available(self, upstream_id: str, model: str) -> bool:
        """检查模型是否可用（不在冷却期内）"""
        key = health_key(upstream_id, model)
        until = self.cooldown_until.get(key, 0)
        if time.time() < until:
            return False
        if key in self.cooldown_until:
            del self.cooldown_until[key]
        return True

    def get_status(self) -> dict:
        """获取当前健康状态快照（key 为 upstream_id:model）"""
        return {
            "fails": dict(self.fails),
            "cooldown": {
                k: max(0, int(v - time.time())) for k, v in self.cooldown_until.items()
            },
        }

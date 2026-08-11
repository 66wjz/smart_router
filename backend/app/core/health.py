"""
故障转移模块 - 模型健康状态跟踪
从 v4 core/health.py 迁移
"""

import logging
import time

log = logging.getLogger("router")


class ModelHealth:
    """模型健康状态管理"""

    def __init__(self, max_fails: int = 3, cooldown_seconds: int = 120):
        self.max_fails = max_fails
        self.cooldown_seconds = cooldown_seconds
        self.fails: dict[str, int] = {}
        self.cooldown_until: dict[str, float] = {}

    def update_config(self, max_fails: int, cooldown_seconds: int) -> None:
        self.max_fails = max_fails
        self.cooldown_seconds = cooldown_seconds

    def record_fail(self, model: str) -> None:
        """记录一次失败，达到阈值则进入冷却"""
        self.fails[model] = self.fails.get(model, 0) + 1
        if self.fails[model] >= self.max_fails:
            self.cooldown_until[model] = time.time() + self.cooldown_seconds
            log.warning(f"模型 {model} 连续失败 {self.fails[model]} 次，冷却 {self.cooldown_seconds}s")

    def record_success(self, model: str) -> None:
        """记录成功，清除失败计数"""
        self.fails.pop(model, None)

    def is_available(self, model: str) -> bool:
        """检查模型是否可用（不在冷却期内）"""
        until = self.cooldown_until.get(model, 0)
        if time.time() < until:
            return False
        if model in self.cooldown_until:
            del self.cooldown_until[model]
        return True

    def get_status(self) -> dict:
        """获取当前健康状态快照"""
        return {
            "fails": dict(self.fails),
            "cooldown": {
                k: max(0, int(v - time.time())) for k, v in self.cooldown_until.items()
            },
        }

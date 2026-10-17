"""
用量采集模块（CH-019）
- 请求级上下文：客户端 Key 信息经 contextvar 从入站端点贯穿到转发层
- UsageBuffer：后台线程批量落库 log_usage，失败不阻塞请求
"""

import contextvars
import logging
import threading
import time

log = logging.getLogger("router")

# Key 贯穿：入站中间件 set → router_service 读取
current_api_key_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_api_key_id", default=None)
current_api_key_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_api_key_name", default="")


def estimate_tokens_by_chars(text: str) -> int:
    """无上游 usage 时的粗略估算：中英混合约 2 字符/token"""
    return len(text or "") // 2


class UsageBuffer:
    """log_usage 批量写入缓冲（后台线程 flush，避免请求路径写库开销）"""

    def __init__(self, retention_days: int = 30):
        self._lock = threading.Lock()
        self._buffer: list[dict] = []
        self.retention_days = retention_days
        self._started = False

    def record(self, entry: dict) -> None:
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= 200:
                self._flush_locked()

    def _flush_locked(self) -> None:
        rows = self._buffer
        self._buffer = []
        if not rows:
            return
        try:
            from app.repositories.usage_repo import UsageRepository
            UsageRepository().insert_many(rows)
        except Exception as e:
            log.warning(f"[usage] 批量落库失败（丢弃 {len(rows)} 条）: {e}")

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def start_worker(self) -> None:
        """启动 5s flush + 按保留天数周期清理的后台线程"""
        if self._started:
            return
        self._started = True

        def _worker():
            while True:
                time.sleep(5)
                try:
                    self.flush()
                except Exception:
                    pass
                # 每小时做一次过期清理
                if int(time.time()) % 3600 < 5:
                    try:
                        from app.repositories.usage_repo import UsageRepository
                        deleted = UsageRepository().purge_older_than(self.retention_days)
                        if deleted:
                            log.info(f"[usage] 清理过期记录 {deleted} 条")
                    except Exception:
                        pass

        t = threading.Thread(target=_worker, daemon=True, name="usage-buffer")
        t.start()
        log.info("[usage] 用量采集后台线程已启动")

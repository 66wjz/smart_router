"""
用量采集模块（CH-019）
- 请求级上下文：客户端 Key 信息经 contextvar 从入站端点贯穿到转发层
- UsageBuffer：后台线程批量落库 log_usage，失败不阻塞请求
"""

import contextvars
import json
import logging
import threading
import time

log = logging.getLogger("router")

# Key 贯穿：入站中间件 set → router_service 读取
current_api_key_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_api_key_id", default=None)
current_api_key_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_api_key_name", default="")

# CH-038：转发报文与尝试链贯穿（适配器 set → 用量采集读取）
current_forward_body: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_forward_body", default=None)
current_response_body: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_response_body", default=None)
current_attempts: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "current_attempts", default=None)
# 入站原始请求体（中间件 set，字符串形式，供详情落库）
current_request_body: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_request_body", default=None)
current_request_headers: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "current_request_headers", default=None)


def parse_cache_tokens(usage: dict | None) -> tuple[int, int]:
    """从上游 usage 中解析缓存 token（CH-038）

    兼容三种常见命名：
      - prompt_tokens_details.cached_tokens（OpenAI 新版）
      - cache_read_input_tokens / cache_creation_input_tokens（Anthropic 风格）
      - prompt_cache_hit_tokens / prompt_cache_miss_tokens（部分中转）

    取不到返回 (0, 0)——缓存命中无法靠字符数估算，不猜。
    """
    if not isinstance(usage, dict) or not usage:
        return 0, 0
    read = write = 0

    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        read = int(details.get("cached_tokens") or 0)

    if not read:
        read = int(usage.get("cache_read_input_tokens") or 0)
    if not write:
        write = int(usage.get("cache_creation_input_tokens") or 0)

    if not read:
        read = int(usage.get("prompt_cache_hit_tokens") or 0)
    if not write:
        write = int(usage.get("prompt_cache_miss_tokens") or 0)

    return max(read, 0), max(write, 0)


def estimate_tokens_by_chars(text: str) -> int:
    """无上游 usage 时的粗略估算：中英混合约 2 字符/token"""
    return len(text or "") // 2


class UsageBuffer:
    """log_usage 批量写入缓冲（后台线程 flush，避免请求路径写库开销）

    CH-038：按 `usage_detail_mode` 决定是否为请求保留详情报文：
      - off        不存
      - error_only 只存失败请求（默认）
      - all        全存
    报文按 `usage_detail_max_bytes` 截断，凭据一律脱敏。
    """

    def __init__(self, retention_days: int = 14, settings_getter=None):
        self._lock = threading.Lock()
        self._buffer: list[dict] = []
        self.retention_days = retention_days
        self._settings = settings_getter  # () -> dict，读 sys_setting（避免循环导入）
        self._started = False

    # ---------- 详情采集策略 ----------

    def _policy(self) -> tuple[str, int]:
        """返回 (mode, max_bytes)；配置缺失时用安全默认"""
        mode, limit = "error_only", 1048576
        if self._settings is None:
            return mode, limit
        try:
            cfg = self._settings() or {}
            mode = str(cfg.get("usage_detail_mode") or mode)
            if mode not in ("off", "error_only", "all"):
                mode = "error_only"
            limit = int(cfg.get("usage_detail_max_bytes") or limit)
        except Exception:
            pass
        return mode, max(1024, min(limit, 262144 * 4))

    @staticmethod
    def _truncate(text: str | None, limit: int) -> str | None:
        """超长报文保留头部 3/4 + 尾部 1/4，并标注被截断的字节数

        保留尾部是必要的：流式的结束标记、末尾 usage、错误尾栈往往在报文最后。
        """
        if not text or len(text) <= limit:
            return text
        keep_head = int(limit * 0.75)
        keep_tail = limit - keep_head
        dropped = len(text) - limit
        return (
            text[:keep_head]
            + f"\n…[truncated {dropped} bytes]…\n"
            + text[-keep_tail:]
        )

    def _build_detail(self, entry: dict, limit: int) -> dict | None:
        """组装详情行；没有任何报文时返回 None（不写空行）"""
        from app.core.logging_setup import _redact

        raw_req = current_request_body.get()
        fwd = current_forward_body.get()
        resp = current_response_body.get()
        headers = current_request_headers.get()
        attempts = current_attempts.get()

        if not any((raw_req, fwd, resp, attempts)):
            return None

        def _clean(text):
            """先脱敏再截断：截断后再脱敏会切断密钥前缀导致正则失效"""
            return self._truncate(_redact(text) if text else text, limit)

        return {
            "request_headers": json.dumps(headers or {}, ensure_ascii=False)
            if headers is not None else None,
            "request_body": _clean(raw_req),
            "forward_body": _clean(fwd),
            "response_body": _clean(resp),
            "attempts": json.dumps(attempts, ensure_ascii=False)
            if attempts is not None else None,
        }

    def record(self, entry: dict) -> None:
        mode, limit = self._policy()
        if mode == "all" or (mode == "error_only" and entry.get("status") != "success"):
            detail = self._build_detail(entry, limit)
            if detail:
                entry["detail"] = detail
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

    def _retention_days(self) -> int:
        """保留天数（CH-038：可由 sys_setting 动态调整，默认 14 天）"""
        if self._settings is not None:
            try:
                cfg = self._settings() or {}
                val = int(cfg.get("usage_retention_days") or self.retention_days)
                if 1 <= val <= 3650:
                    return val
            except Exception:
                pass
        return self.retention_days

    def start_worker(self) -> None:
        """启动 5s flush + 按保留天数周期清理的后台线程（主表与详情表同步清理）"""
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
                        UsageRepository().purge_older_than(self._retention_days())
                    except Exception:
                        pass

        t = threading.Thread(target=_worker, daemon=True, name="usage-buffer")
        t.start()
        log.info("[usage] 用量采集后台线程已启动")

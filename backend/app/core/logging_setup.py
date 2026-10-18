"""
运行日志落文件 + 请求上下文（CH-025）

背景：原来只有控制台日志进 journal，看不到「请求体长什么样」，
出错只知道崩在哪一行，无法定位客户端到底发了什么。

- 文件日志：RotatingFileHandler 写 logs/smart-router.log（10MB × 5 自动轮转）
- 请求上下文：ASGI 中间件缓存 /v1 请求体并解析出 model / stream / messages，
  便于异常时输出可追溯的一行；请求体非法 JSON 时立刻告警并留摘要
"""

import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("router")
_access_log = logging.getLogger("access")

LOG_FILE_NAME = "smart-router.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5
DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

# 日志摘要里抹掉疑似密钥（sk-xxxx），避免把凭据写进日志
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{4,}")


def log_dir() -> Path:
    """日志目录，可用 SMART_ROUTER_LOG_DIR 覆盖"""
    return Path(os.environ.get("SMART_ROUTER_LOG_DIR") or DEFAULT_LOG_DIR)


def log_file() -> Path:
    return log_dir() / LOG_FILE_NAME


def setup_file_logging() -> Path | None:
    """给 root logger 挂轮转文件处理器；失败只告警，不阻断启动"""
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = log_file().resolve()
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, RotatingFileHandler) and \
                    Path(getattr(handler, "baseFilename", "")).resolve() == path:
                return path
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES,
                                      backupCount=BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(handler)
        log.info(f"文件日志已启用: {path}")
        return path
    except Exception:
        log.warning("文件日志初始化失败，仅输出到控制台", exc_info=True)
        return None


def tail_logs(lines: int = 200, keyword: str = "") -> dict:
    """读取日志尾部（管理接口用）。keyword 非空时只返回含该关键词的行"""
    path = log_file()
    try:
        limit = max(1, min(int(lines or 200), 5000))
    except (TypeError, ValueError):
        limit = 200
    if not path.is_file():
        return {"file": str(path), "size_bytes": 0, "returned": 0,
                "keyword": keyword, "content": ""}
    size = path.stat().st_size
    # 只读尾部最多 1MB，避免大文件整读
    read_bytes = min(size, 1024 * 1024)
    with open(path, "rb") as f:
        f.seek(size - read_bytes)
        chunk = f.read().decode("utf-8", "ignore")
    rows = chunk.splitlines()
    if read_bytes < size and rows:
        rows = rows[1:]  # 首行可能被截断，丢弃
    if keyword:
        rows = [r for r in rows if keyword in r]
    shown = rows[-limit:]
    return {
        "file": str(path),
        "size_bytes": size,
        "returned": len(shown),
        "keyword": keyword,
        "content": "\n".join(shown),
    }


def _redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1****", text)


def _snippet(raw: bytes, limit: int = 300) -> str:
    """请求体摘要：截断 + 单行化 + 抹掉疑似密钥"""
    if not raw:
        return ""
    text = raw[: limit * 4].decode("utf-8", "ignore")
    return _redact(text.replace("\r", " ").replace("\n", " "))[:limit]


def _parse_body(body: bytes) -> dict:
    """从请求体解析路由关键信息；非 JSON / 非对象时标记 invalid"""
    if not body:
        return {"invalid": True, "reason": "empty", "model": "", "stream": False, "messages": None}
    try:
        data = json.loads(body)
    except Exception:
        return {"invalid": True, "reason": "bad_json", "model": "", "stream": False, "messages": None}
    if not isinstance(data, dict):
        return {"invalid": True, "reason": "not_object", "model": "", "stream": False, "messages": None}
    msgs = data.get("messages")
    return {
        "invalid": False,
        "reason": "",
        "model": str(data.get("model") or ""),
        "stream": bool(data.get("stream")),
        "messages": len(msgs) if isinstance(msgs, list) else None,
    }


def describe_request(request) -> str:
    """异常兜底用的一行请求上下文（含请求体摘要）"""
    state = getattr(request, "state", None)
    info = getattr(state, "body_info", None) or {}
    client = request.client.host if request.client else "-"
    parts = [
        f"client={client}",
        f"model={info.get('model') or '-'}",
        f"stream={info.get('stream')}",
    ]
    if info.get("messages") is not None:
        parts.append(f"messages={info['messages']}")
    if info.get("invalid"):
        parts.append(f"body=INVALID({info.get('reason')})")
    snippet = getattr(state, "request_snippet", "")
    if snippet:
        parts.append(f"body_snippet={snippet}")
    return " ".join(parts)


class RequestContextMiddleware:
    """ASGI 中间件：只对 /v1 请求缓存请求体、输出访问日志

    用纯 ASGI 实现（不依赖 BaseHTTPMiddleware），把请求体放进 scope["state"]，
    这样路由层与异常兜底都能拿到同一份上下文。
    """

    def __init__(self, app, prefix: str = "/v1/"):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not scope.get("path", "").startswith(self.prefix):
            return await self.app(scope, receive, send)

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunks.append(message.get("body", b"") or b"")
            if not message.get("more_body"):
                break
        body = b"".join(chunks)

        info = _parse_body(body)
        state = scope.setdefault("state", {})
        state["body_info"] = info
        state["request_snippet"] = _snippet(body)

        client = scope.get("client") or ("-", 0)
        started = time.time()
        replayed = False

        async def replay():
            # 首次交还缓存的请求体；之后交还原 receive（保持断开检测语义）
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                _log_access(scope, info, state, client, started, message["status"])
            await send(message)

        if info.get("invalid"):
            log.warning(
                f"请求体无法解析 | {scope.get('method')} {scope.get('path')} "
                f"client={client[0]} reason={info.get('reason')} "
                f"len={len(body)} snippet={state['request_snippet']}"
            )

        await self.app(scope, replay, send_wrapper)


def _log_access(scope, info: dict, state: dict, client, started: float, status: int) -> None:
    parts = [
        f"status={status}",
        f"elapsed={time.time() - started:.2f}s",
        f"client={client[0]}",
        f"model={info.get('model') or '-'}",
        f"stream={info.get('stream')}",
    ]
    if info.get("messages") is not None:
        parts.append(f"messages={info['messages']}")
    if info.get("invalid"):
        parts.append(f"body=INVALID({info.get('reason')})")
    line = f"{scope.get('method', '?')} {scope.get('path', '?')} {' '.join(parts)}"
    if status >= 400:
        snippet = state.get("request_snippet", "")
        tail = f" | body_snippet={snippet}" if snippet else ""
        _access_log.warning(line + tail)
    else:
        _access_log.info(line)

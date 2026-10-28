"""CH-052 会话亲和（缓存优先路由）

解决问题：聚合按请求换源 / Key 池轮询 / 前缀变化会让同一会话的请求落到不同
提供商或账号上，上游 prompt cache 是按「提供商 + 账号 + 前缀」隔离的，一换就
整段重算。

做法（不依赖客户端、不依赖号池）：
- 用请求内容算「会话指纹」：优先 user 字段，其次第一条 user 消息（不 hash 全量）；
- 新会话按 `负载 / 权重` 选一个目标并钉住 (upstream, model, key)；
- 同会话后续请求直接用钉子，只有目标失败/冷却/不在候选时才重钉；
- 短请求不钉；状态在内存（TTL + LRU），重启后重新钉。
"""

import hashlib
import threading
import time
from collections import OrderedDict, deque
from contextvars import ContextVar

# 当前请求的「优先 Key」与「实际使用 Key」，由路由器设置，KeyPool 读取/回写。
# 用 contextvar 而不是改所有适配器签名，流式/非流式都在同一请求任务里。
current_preferred_key: ContextVar[str | None] = ContextVar("affinity_preferred_key", default=None)
current_used_key: ContextVar[str | None] = ContextVar("affinity_used_key", default=None)


class AffinityEntry:
    """一条会话钉子"""

    __slots__ = ("upstream", "model", "key", "expires_at", "last_seen")

    def __init__(self, upstream: str, model: str, key: str | None, expires_at: float):
        self.upstream = upstream
        self.model = model
        self.key = key
        self.expires_at = expires_at
        self.last_seen = time.time()


def _content_text(content) -> str:
    """消息 content → 纯文本（多模态只取 text part）"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def _first_user_text(body: dict) -> str | None:
    """取第一条 user 消息文本；兼容 chat / anthropic / responses / completions"""
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                text = _content_text(msg.get("content"))
                if text.strip():
                    return text
        if messages and isinstance(messages[0], dict):
            text = _content_text(messages[0].get("content"))
            if text.strip():
                return text
        return None

    # OpenAI Responses：input 可以是字符串或消息数组
    inp = body.get("input")
    if isinstance(inp, str):
        return inp if inp.strip() else None
    if isinstance(inp, list):
        for item in inp:
            if isinstance(item, dict) and item.get("role") == "user":
                text = _content_text(item.get("content"))
                if text.strip():
                    return text
        for item in inp:
            if isinstance(item, dict):
                text = _content_text(item.get("content"))
                if text.strip():
                    return text
        return None

    prompt = body.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt
    return None


def _all_text(body: dict) -> str:
    """估算 prompt 体量用的全量文本（不参与指纹）"""
    chunks = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                chunks.append(_content_text(msg.get("content")))
    elif isinstance(body.get("input"), str):
        chunks.append(body["input"])
    elif isinstance(body.get("input"), list):
        for item in body["input"]:
            if isinstance(item, dict):
                chunks.append(_content_text(item.get("content")))
    if isinstance(body.get("prompt"), str):
        chunks.append(body["prompt"])
    system = body.get("system")
    if isinstance(system, str):
        chunks.append(system)
    return "\n".join(c for c in chunks if c)


class SessionAffinity:
    """会话亲和表 + 新会话放置（内存态，线程安全）"""

    LOAD_WINDOW_SECONDS = 300

    def __init__(self):
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, AffinityEntry] = OrderedDict()
        self._recent: dict[str, deque] = {}
        self._active: dict[str, int] = {}
        self.ttl_seconds = 2700
        self.max_entries = 20000
        self.min_prompt_tokens = 2000

    def configure(self, ttl_seconds: int | None = None, max_entries: int | None = None,
                  min_prompt_tokens: int | None = None) -> None:
        with self._lock:
            if ttl_seconds is not None:
                self.ttl_seconds = max(60, int(ttl_seconds))
            if max_entries is not None:
                self.max_entries = max(100, int(max_entries))
            if min_prompt_tokens is not None:
                self.min_prompt_tokens = max(0, int(min_prompt_tokens))

    # ---------- 会话指纹 ----------

    def fingerprint(self, model: str, body: dict) -> str | None:
        """会话指纹：不依赖客户端改动，只从请求内容生成（16 位 SHA-256）"""
        user = body.get("user")
        if isinstance(user, str) and user.strip():
            raw = f"{model}\x00user:{user}"
        else:
            text = _first_user_text(body)
            if not text:
                return None
            raw = f"{model}\x00{text}"
        return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16]

    def estimate_prompt_tokens(self, body: dict) -> int:
        """粗估 prompt tokens（只用于短请求跳过，不做计费）"""
        return max(1, len(_all_text(body)) // 3)

    # ---------- 表操作 ----------

    def lookup(self, key: str) -> AffinityEntry | None:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._drop(key)
                return None
            entry.expires_at = now + self.ttl_seconds
            entry.last_seen = now
            self._entries.move_to_end(key)
            return entry

    def bind(self, key: str, upstream: str, model: str, key_value: str | None = None) -> AffinityEntry:
        now = time.time()
        with self._lock:
            old = self._entries.get(key)
            if old is not None:
                # 同 upstream 重绑也要先把旧计数减掉，否则 active 会重复累加
                self._active[old.upstream] = max(0, self._active.get(old.upstream, 0) - 1)
            entry = AffinityEntry(upstream, model, key_value, now + self.ttl_seconds)
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._active[upstream] = self._active.get(upstream, 0) + 1
            while len(self._entries) > self.max_entries:
                _, victim = self._entries.popitem(last=False)
                self._active[victim.upstream] = max(0, self._active.get(victim.upstream, 0) - 1)
            return entry

    def update_key(self, key: str, key_value: str | None) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and key_value:
                entry.key = key_value

    def unbind(self, key: str) -> None:
        with self._lock:
            self._drop(key)

    def _drop(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._active[entry.upstream] = max(0, self._active.get(entry.upstream, 0) - 1)

    # ---------- 负载与新会话放置 ----------

    def record_request(self, upstream: str) -> None:
        now = time.time()
        with self._lock:
            queue = self._recent.setdefault(upstream, deque())
            queue.append(now)
            self._prune(queue, now)

    def choose(self, candidates: list[dict]) -> dict | None:
        """按 score = (近 5 分钟请求数 + 活跃会话数) / weight 取最小"""
        if not candidates:
            return None
        now = time.time()
        with self._lock:
            best = None
            best_score = None
            for cand in candidates:
                upstream = cand.get("upstream") or ""
                weight = max(1, int(cand.get("weight") or 1))
                queue = self._recent.get(upstream)
                if queue is not None:
                    self._prune(queue, now)
                    recent = len(queue)
                else:
                    recent = 0
                load = recent + self._active.get(upstream, 0)
                score = load / weight
                if best_score is None or score < best_score:
                    best, best_score = cand, score
            return best

    def _prune(self, queue: deque, now: float) -> None:
        cutoff = now - self.LOAD_WINDOW_SECONDS
        while queue and queue[0] < cutoff:
            queue.popleft()

    # ---------- 观测 ----------

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            for queue in self._recent.values():
                self._prune(queue, now)
            return {
                "entries": len(self._entries),
                "active": dict(self._active),
                "recent": {k: len(v) for k, v in self._recent.items() if v},
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
                "min_prompt_tokens": self.min_prompt_tokens,
            }

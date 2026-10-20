"""
OpenAI 格式适配器 - 处理标准 OpenAI API 格式的请求转发
从 v4 upstream/openai_adapter.py 迁移，import 路径改为 app 包结构
"""

import asyncio
import copy
import json
import logging
import random
import time

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import AppConfig
from app.core.health import ModelHealth
from app.core.usage import (
    current_attempts,
    current_forward_body,
    current_response_body,
)

log = logging.getLogger("router")

SMART_RETRYABLE_STATUS = (429, 500, 502, 503, 504)

# CH-038：详情报文采集上限（与 sys_setting.usage_detail_max_bytes 的默认值对齐；
# 这里只是避免超大对象在内存里无限拷贝，最终截断由 UsageBuffer 按配置执行）
_MAX_CAPTURE = 2 * 1024 * 1024


def _capture_forward(modified: dict) -> None:
    """记录实际发给上游的请求体（CH-038，供详情页 FORWARDED 栏）"""
    try:
        current_forward_body.set(json.dumps(modified, ensure_ascii=False)[:_MAX_CAPTURE])
    except Exception:
        pass


def _capture_response(data) -> None:
    """记录上游响应体（CH-038，供详情页 RESPONSE 栏）"""
    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False)
        elif isinstance(data, bytes):
            text = data.decode("utf-8", "ignore")
        else:
            text = str(data)
        current_response_body.set(text[:_MAX_CAPTURE])
    except Exception:
        pass


def _elapsed_ms(t0: float) -> int:
    """距 t0 的毫秒数（CH-038 尝试链耗时）"""
    try:
        return int((time.time() - t0) * 1000)
    except Exception:
        return 0


def _note_attempt(upstream_id: str, model: str, http_status, ms: int,
                  error: str | None = None) -> None:
    """追加一条候选尝试记录（CH-038，供详情页重试链）"""
    try:
        items = current_attempts.get()
        if items is None:
            items = []
            current_attempts.set(items)
        items.append({
            "upstream": upstream_id,
            "model": model,
            "http_status": http_status,
            "ms": ms,
            "error": (error or None) and str(error)[:300],
        })
    except Exception:
        pass


def _normalize_messages(body: dict) -> None:
    """出站前规范化消息角色（CH-037）

    OpenAI 后期把 `system` 更名为 `developer`，二者语义等价。但部分上游/中转
    （本环境号池实测）只认 `system`，遇到 `developer` 直接返回
    400 unsupported message role: developer。

    客户端（如 DSH）把 developer 放在首条消息里，导致该请求在任何候选上都必然
    失败；多源同名聚合时表现为「所有模型均不可用」503，且无法通过重试恢复。

    这里就地改写为 system：只改 role，不动 content 与消息顺序。
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "developer":
            msg["role"] = "system"


def _build_endpoint(base_url: str, path: str) -> str:
    """拼接请求端点，容错 base_url 误填完整 URL（已含目标路径时直接使用）"""
    base = (base_url or "").rstrip("/")
    if not base:
        return ""
    if base.endswith(path):
        return base
    return f"{base}{path}"


def _extract_wrapped_error(payload) -> str | None:
    """识别「HTTP 200 + 错误包」这种软失败（CH-040）

    部分上游/号池把业务错误包在 200 响应体里返回，而不是用 4xx/5xx。
    真实案例（号池 buddy 渠道）：
        {"choices":[],"error":{"message":"...Illegal API invocation from
         an unapproved channel","code":"INVALID_REQUEST","status":400}}

    这类响应一旦被当成成功，会同时错三件事：记账记成 success、详情按成功
    策略丢弃、且不会切换到下一个源重试。

    返回错误摘要字符串（判为软失败），或 None（视为正常响应）。
    """
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if not err:
        return None
    # 有正常业务载荷时不算软失败（个别上游会同时带 error 和 choices）
    for key in ("choices", "output", "data", "content"):
        if payload.get(key):
            return None
    if isinstance(err, dict):
        parts = [str(x) for x in (err.get("message"), err.get("code"), err.get("status")) if x]
        text = " | ".join(parts) if parts else json.dumps(err, ensure_ascii=False)
    else:
        text = str(err)
    return (text[:300] or "上游返回错误包（无详细说明）")


def _parse_sse_error_line(line: str) -> str | None:
    """从 SSE 单行判断是否为错误包（CH-040）"""
    text = (line or "").strip()
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    return _extract_wrapped_error(data)


def _sr_backoff(sr_cfg: dict, same_key_index: int) -> float:
    """智能重试同 Key 退避秒数：backoff_ms 逐级升级 + ±jitter 抖动"""
    backoff_ms = sr_cfg.get("backoff_ms", [500, 1500]) or [500, 1500]
    jitter = sr_cfg.get("jitter", 0.2)
    base = backoff_ms[min(same_key_index, len(backoff_ms) - 1)] / 1000.0
    if jitter:
        base *= 1 + random.uniform(-jitter, jitter)
    return max(base, 0.05)


class _RetryLoop:
    """智能重试预算控制（CH-012）
    开关关闭：budget = Key 数，行为与旧版一致（仅 401/403/429/超时/连接异常 换 Key）
    开关打开：budget = Key 数 + extra_attempts；5xx 纳入可重试；同 Key 重试前退避"""

    def __init__(self, app_config: AppConfig, upstream_id: str, model: str, keys: list[str]):
        self.enabled = app_config.is_smart_retry_enabled(upstream_id)
        self.cfg = app_config.smart_retry_config
        extra = self.cfg.get("extra_attempts", 2) if self.enabled else 0
        self.budget = len(keys) + extra
        self.retries = 0
        self.same_key_retries = 0
        self.prev_key: str | None = None
        self.upstream_id = upstream_id
        self.model = model

    async def before_attempt(self, api_key: str) -> None:
        """每次拿到 Key 后调用：同 Key 重试时先退避"""
        if self.enabled and self.prev_key is not None and api_key == self.prev_key:
            delay = _sr_backoff(self.cfg, self.same_key_retries)
            self.same_key_retries += 1
            log.warning(f"[smart-retry] {self.upstream_id}/{self.model.split('/')[-1]} "
                        f"退避 {int(delay * 1000)}ms 后同 Key 重试")
            await asyncio.sleep(delay)

    def on_failure(self, api_key: str) -> None:
        self.retries += 1
        self.prev_key = api_key

    def retriable_status(self, status_code: int) -> bool:
        """开关打开时 5xx 可重试（429 换 Key 是旧行为，不在此列）"""
        return self.enabled and status_code in (500, 502, 503, 504)

    def log_retry(self, reason: str) -> None:
        if self.enabled:
            log.warning(f"[smart-retry] {self.upstream_id}/{self.model.split('/')[-1]} {reason}，重试")

    def response_headers(self) -> dict:
        return {
            "X-Served-By": f"{self.upstream_id}/{self.model}",
            "X-Retry-Count": str(self.retries),
        }


async def try_non_stream(
    model: str,
    upstream_id: str,
    body: dict,
    request_headers: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
    max_output: int | None = None,
) -> JSONResponse | None:
    """尝试非流式请求，成功返回 JSONResponse，失败返回 None
    Key 池循环：401/403/429/连接超时/响应超时视为该 Key 失败，换下一个 Key 重试
    使用 send(stream=True)+aread()+显式 aclose，避免超时取消产生脏连接阻塞后续请求"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    if not base_url or not keys:
        health.record_fail(upstream_id, model)
        return None

    modified = copy.deepcopy(body)
    modified["model"] = model
    _normalize_messages(modified)
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    url = _build_endpoint(base_url, "/v1/chat/completions")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    _capture_forward(modified)  # CH-038：实际转发体

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        t_attempt = time.time()  # CH-038：单次尝试计时
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=modified, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except (asyncio.TimeoutError, httpx.TimeoutException):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 连接超时 ({timeout_sec}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 连接超时 ({timeout_sec}s)，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), "连接超时")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 连接异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 连接异常: {e}，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), f"连接异常: {e}")
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 响应超时 ({timeout_sec}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 响应超时 ({timeout_sec}s)，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), "响应超时")
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 响应异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 响应异常: {e}，换下一个 Key")
            continue

        if resp.status_code == 200:
            await resp.aclose()
            # CH-040：200 但响应体是错误包 → 按失败处理并切换候选
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            wrapped_error = _extract_wrapped_error(parsed)
            if wrapped_error:
                app_config.key_pool.record_fail(upstream_id, api_key)
                rl.on_failure(api_key)
                rl.log_retry(f"响应体错误包: {wrapped_error[:80]}")
                log.warning(f"模型 {model.split('/')[-1]} 返回 200 但响应体是错误包: "
                            f"{wrapped_error[:120]}，视为失败并重试")
                _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt), wrapped_error)
                _capture_response(raw)
                health.record_fail(upstream_id, model)
                continue
            app_config.key_pool.record_success(upstream_id, api_key)
            health.record_success(upstream_id, model)
            _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt))
            _capture_response(raw)  # CH-038：上游响应体
            return JSONResponse(status_code=200, content=parsed, headers=rl.response_headers())
        await resp.aclose()
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 返回 HTTP {resp.status_code}")
            log.warning(f"Key 池 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
            _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                          "Key 鉴权/限流失败，换 Key")
            continue
        if rl.retriable_status(resp.status_code):
            rl.on_failure(api_key)
            rl.log_retry(f"HTTP {resp.status_code}")
            _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                          "可重试状态码")
            continue
        health.record_fail(upstream_id, model)
        # CH-037：带上上游响应体摘要，否则只知道 400 不知道为什么（排查时被迫直连号池）
        detail = _extract_error_detail(raw, resp.status_code)
        log.warning(f"模型 {model.split('/')[-1]} 返回错误: HTTP {resp.status_code} {detail}")
        _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt), detail)
        _capture_response(raw)  # CH-038：失败响应体也要留（排查最关键）
        return None
    return None


async def try_stream(
    model: str,
    upstream_id: str,
    body: dict,
    request_headers: dict,
    first_chunk_timeout: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
    health: ModelHealth,
    max_output: int | None = None,
    *,
    response_timeout: float | None = None,
) -> StreamingResponse | None:
    """尝试流式请求，首包成功返回 StreamingResponse，失败/超时返回 None
    Key 池循环：401/403/429/首包超时/空响应/连接异常视为该 Key 失败，换下一个 Key 重试

    response_timeout: 等待上游返回「响应头」的超时（秒）。None = 不限（保持旧行为）。
    与 first_chunk_timeout 分属两个阶段：先等响应头，拿到后才等首包内容。"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    keys = app_config.get_upstream_keys(upstream_id)
    if not base_url or not keys:
        health.record_fail(upstream_id, model)
        return None

    modified = copy.deepcopy(body)
    modified["model"] = model
    _normalize_messages(modified)
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    url = _build_endpoint(base_url, "/v1/chat/completions")
    if not url:
        health.record_fail(upstream_id, model)
        return None

    _capture_forward(modified)  # CH-038：实际转发体

    rl = _RetryLoop(app_config, upstream_id, model, keys)
    for _ in range(rl.budget):
        t_attempt = time.time()  # CH-038：单次尝试计时
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        await rl.before_attempt(api_key)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            send_coro = http_client.send(
                http_client.build_request("POST", url, json=modified, headers=headers),
                stream=True,
            )
            # 等响应头：有配置就走 wait_for，未配置保持旧行为（受 httpx 全局超时管）
            resp = (await asyncio.wait_for(send_coro, timeout=response_timeout)
                    if response_timeout else await send_coro)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"流式响应头超时 ({response_timeout}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 流式响应头超时 ({response_timeout}s)，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), "流式响应头超时")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"Key 流式连接异常: {e}")
            log.warning(f"Key 池 [{upstream_id}] Key 流式连接异常: {e}，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), f"流式连接异常: {e}")
            continue

        if resp.status_code != 200:
            err_raw = await resp.aread()
            await resp.aclose()
            if resp.status_code in (401, 403, 429):
                app_config.key_pool.record_fail(upstream_id, api_key)
                rl.on_failure(api_key)
                rl.log_retry(f"Key 返回 HTTP {resp.status_code}")
                log.warning(f"Key 池 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
                _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                              "Key 鉴权/限流失败，换 Key")
                continue
            if rl.retriable_status(resp.status_code):
                rl.on_failure(api_key)
                rl.log_retry(f"流式 HTTP {resp.status_code}（首字节前）")
                _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt),
                              "可重试状态码（首字节前）")
                continue
            health.record_fail(upstream_id, model)
            # CH-037：带上上游响应体摘要，否则只知道 400 不知道为什么
            detail = _extract_error_detail(err_raw, resp.status_code)
            log.warning(f"模型 {model.split('/')[-1]} 流式返回错误: HTTP {resp.status_code} {detail}")
            _note_attempt(upstream_id, model, resp.status_code, _elapsed_ms(t_attempt), detail)
            _capture_response(err_raw)  # CH-038：失败响应体
            return None

        line_iter = resp.aiter_lines()
        try:
            first_line = await asyncio.wait_for(
                line_iter.__anext__(), timeout=first_chunk_timeout
            )
        except StopAsyncIteration:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry("流式空响应")
            log.warning(f"Key 池 [{upstream_id}] Key 流式空响应，换下一个 Key")
            _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt), "流式空响应")
            continue
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"首包超时 ({first_chunk_timeout}s)")
            log.warning(f"Key 池 [{upstream_id}] Key 首包超时 ({first_chunk_timeout}s)，换下一个 Key")
            _note_attempt(upstream_id, model, None, _elapsed_ms(t_attempt), "首包超时")
            continue

        # CH-040：首行若为「200 + 错误包」，此时还没向客户端发任何字节，
        # 仍然可以按失败处理并切换候选；不能把业务错误当成功。
        first_error = _parse_sse_error_line(first_line)
        if first_error:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            rl.on_failure(api_key)
            rl.log_retry(f"响应体错误包: {first_error[:80]}")
            log.warning(f"模型 {model.split('/')[-1]} 返回 200 但响应体是错误包: {first_error[:120]}，视为失败并重试")
            _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt), first_error)
            _capture_response(first_line)
            health.record_fail(upstream_id, model)
            continue

        app_config.key_pool.record_success(upstream_id, api_key)
        health.record_success(upstream_id, model)
        _note_attempt(upstream_id, model, 200, _elapsed_ms(t_attempt))

        async def generate():
            head_chunks: list[str] = []
            tail_chunks: list[str] = []
            try:
                if first_line:
                    yield first_line + "\n\n"
                    head_chunks.append(first_line)
                async for line in line_iter:
                    if line:
                        yield line + "\n\n"
                        # CH-038：只留头部与尾部片段，避免把整段流式内容堆在内存
                        if len(head_chunks) < 20:
                            head_chunks.append(line)
                        else:
                            tail_chunks.append(line)
                            if len(tail_chunks) > 20:
                                tail_chunks.pop(0)
            except Exception as e:
                log.error(f"流式传输中断: {model.split('/')[-1]} {e}")
                health.record_fail(upstream_id, model)
            finally:
                # CH-038：把流式首尾片段作为 RESPONSE 详情（完整流不落库）
                try:
                    current_response_body.set(
                        "\n".join(head_chunks + (["…"] + tail_chunks if tail_chunks else []))
                        [:_MAX_CAPTURE]
                    )
                except Exception:
                    pass
                try:
                    await resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream", headers=rl.response_headers())
    return None


def _extract_error_detail(raw: bytes, status_code: int) -> str:
    """从非 200 响应体中提取具体错误信息"""
    text = ""
    try:
        parsed = json.loads(raw)
        err = parsed.get("error")
        if isinstance(err, dict):
            text = err.get("message") or err.get("code") or json.dumps(err, ensure_ascii=False)
        elif err:
            text = str(err)
        else:
            text = json.dumps(parsed, ensure_ascii=False)[:300]
    except Exception:
        text = raw.decode("utf-8", "ignore")[:300]
    return (text or "").strip()


async def test_non_stream(
    model: str,
    upstream_id: str,
    body: dict,
    timeout_sec: float,
    http_client: httpx.AsyncClient,
    app_config: AppConfig,
) -> tuple[str | None, str | None]:
    """管理端单模型测试：返回 (回复文本, 错误信息)
    错误信息具体到 HTTP 状态码+响应体 / 连接超时 / 响应超时 / 连接异常；全部 Key 失败时返回最后一次错误"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/") if upstream else ""
    keys = app_config.get_upstream_keys(upstream_id)
    url = _build_endpoint(base_url, "/v1/chat/completions")
    if not url:
        return None, "上游未配置 Base URL"
    if not keys:
        return None, "上游未配置可用 API Key"

    modified = copy.deepcopy(body)
    modified["model"] = model
    _normalize_messages(modified)

    last_error = "上游所有 Key 均失败"
    for _ in range(len(keys)):
        api_key = app_config.key_pool.pick(upstream_id, keys)
        if not api_key:
            break
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = await asyncio.wait_for(
                http_client.send(
                    http_client.build_request("POST", url, json=modified, headers=headers),
                    stream=True,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接超时（{timeout_sec}s）"
            log.warning(f"测试 [{upstream_id}] Key 连接超时，换下一个 Key")
            continue
        except Exception as e:
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"连接异常: {e}"
            log.warning(f"测试 [{upstream_id}] Key 连接异常: {e}，换下一个 Key")
            continue

        try:
            raw = await asyncio.wait_for(resp.aread(), timeout=timeout_sec)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应超时（{timeout_sec}s）"
            log.warning(f"测试 [{upstream_id}] Key 响应超时，换下一个 Key")
            continue
        except Exception as e:
            await resp.aclose()
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"响应读取异常: {e}"
            log.warning(f"测试 [{upstream_id}] Key 响应异常: {e}，换下一个 Key")
            continue

        if resp.status_code == 200:
            await resp.aclose()
            app_config.key_pool.record_success(upstream_id, api_key)
            try:
                data = json.loads(raw)
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
            except Exception:
                content = None
            return content or "（无文本回复）", None
        await resp.aclose()
        detail = _extract_error_detail(raw, resp.status_code)
        if resp.status_code in (401, 403, 429):
            app_config.key_pool.record_fail(upstream_id, api_key)
            last_error = f"HTTP {resp.status_code} {detail}（已换 Key 重试）"
            log.warning(f"测试 [{upstream_id}] Key 返回 HTTP {resp.status_code}，换下一个 Key")
            continue
        return None, f"HTTP {resp.status_code} {detail}".strip()
    return None, last_error

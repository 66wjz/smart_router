"""
OpenAI 格式适配器 - 处理标准 OpenAI API 格式的请求转发
支持非流式和流式两种模式。
"""

import asyncio
import copy
import logging

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from core.config import AppConfig
from core.health import ModelHealth

log = logging.getLogger("router")


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
    """尝试非流式请求，成功返回 JSONResponse，失败返回 None"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    api_key = upstream.get("api_key", "")

    modified = copy.deepcopy(body)
    modified["model"] = model

    # max_tokens 自动调整
    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    # 始终使用 upstream 自带的 Key，客户端 Key 仅用于路由鉴权（不透传）
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url}/v1/chat/completions"

    try:
        resp = await asyncio.wait_for(
            http_client.post(url, json=modified, headers=headers),
            timeout=timeout_sec,
        )
        if resp.status_code == 200:
            health.record_success(model)
            return JSONResponse(status_code=200, content=resp.json())
        else:
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} 返回错误: HTTP {resp.status_code}")
            return None
    except (asyncio.TimeoutError, httpx.TimeoutException):
        health.record_fail(model)
        log.warning(f"模型 {model.split('/')[-1]} 响应超时 ({timeout_sec}s)")
        return None
    except Exception as e:
        health.record_fail(model)
        log.warning(f"模型 {model.split('/')[-1]} 请求异常: {e}")
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
) -> StreamingResponse | None:
    """尝试流式请求，首包成功返回 StreamingResponse，失败/超时返回 None"""
    upstream = app_config.get_upstream(upstream_id)
    base_url = upstream.get("base_url", "").rstrip("/")
    api_key = upstream.get("api_key", "")

    modified = copy.deepcopy(body)
    modified["model"] = model

    if max_output and "max_tokens" in modified and modified["max_tokens"] > max_output:
        log.info(f"  max_tokens 调整: {modified['max_tokens']} → {max_output} (模型上限)")
        modified["max_tokens"] = max_output

    # 始终使用 upstream 自带的 Key，客户端 Key 仅用于路由鉴权（不透传）
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url}/v1/chat/completions"

    try:
        resp = await http_client.send(
            http_client.build_request("POST", url, json=modified, headers=headers),
            stream=True,
        )

        if resp.status_code != 200:
            error_text = await resp.aread()
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} 流式返回错误: HTTP {resp.status_code}")
            return None

        # 等待首包
        line_iter = resp.aiter_lines()
        try:
            first_line = await asyncio.wait_for(
                line_iter.__anext__(), timeout=first_chunk_timeout
            )
        except StopAsyncIteration:
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} 流式空响应")
            return None
        except (asyncio.TimeoutError, httpx.TimeoutException):
            await resp.aclose()
            health.record_fail(model)
            log.warning(f"模型 {model.split('/')[-1]} 首包超时 ({first_chunk_timeout}s)")
            return None

        # 首包到达，开始流式传输
        health.record_success(model)

        async def generate():
            try:
                if first_line:
                    yield first_line + "\n\n"
                async for line in line_iter:
                    if line:
                        yield line + "\n\n"
            except Exception as e:
                log.error(f"流式传输中断: {model.split('/')[-1]} {e}")
                health.record_fail(model)
            finally:
                try:
                    await resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        log.warning(f"模型 {model.split('/')[-1]} 流式连接异常: {e}")
        health.record_fail(model)
        return None

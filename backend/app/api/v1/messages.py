"""
v1 Anthropic Messages 入站接口 - POST /v1/messages（CH-009）
Anthropic 格式请求 → 内部统一 openai chat 格式 → RouterService 全链路 → 响应转回 Anthropic 格式
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.router_service import RouterService
from app.upstream.anthropic_adapter import (
    OpenaiToAnthropicSSE,
    convert_request_anthropic_to_openai,
    convert_response_openai_to_anthropic,
)
from app.upstream.headers import ascii_safe_headers

log = logging.getLogger("router")

router = APIRouter(tags=["v1-messages"])


def _anthropic_error(status_code: int, message: str) -> JSONResponse:
    """构造 Anthropic 协议错误响应（客户端 SDK 依赖该格式解析错误）"""
    etype = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        429: "rate_limit_error",
        503: "api_error",
    }.get(status_code, "api_error")
    return JSONResponse(status_code=status_code, content={
        "type": "error",
        "error": {"type": etype, "message": message},
    })


@router.post("/v1/messages")
async def messages(request: Request):
    """Anthropic 兼容 Messages 接口：客户端用 Anthropic SDK 即可调任意上游模型"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={
            "type": "error", "error": {"type": "invalid_request_error", "message": "请求体不是合法 JSON"},
        })
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={
            "type": "error", "error": {"type": "invalid_request_error", "message": "请求体必须是 JSON 对象"},
        })
    if not body.get("model"):
        return JSONResponse(status_code=400, content={
            "type": "error", "error": {"type": "invalid_request_error", "message": "model 参数缺失"},
        })

    model = body["model"]
    openai_body = convert_request_anthropic_to_openai(body)
    key_groups = getattr(request.state, "key_groups", None)
    svc: RouterService = request.app.state.router_service
    log.info(f"[/v1/messages] {model} stream={bool(body.get('stream'))} key={getattr(request.state, 'key_name', '')}")

    try:
        resp = await svc.chat_completions(openai_body, key_groups, protocol="anthropic")
    except HTTPException as e:
        return _anthropic_error(e.status_code, str(e.detail) if e.detail else "上游服务不可用")

    if isinstance(resp, StreamingResponse):
        converter = OpenaiToAnthropicSSE(model)

        async def anthropic_stream():
            try:
                async for chunk in resp.body_iterator:
                    text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "ignore")
                    for ev in converter.feed(text):
                        yield ev
                for ev in converter.close():
                    yield ev
            except Exception as e:
                log.error(f"/v1/messages 流式转换中断: {e}")

        return StreamingResponse(
            anthropic_stream(),
            media_type="text/event-stream",
            headers=ascii_safe_headers({k: v for k, v in resp.headers.items() if k.lower().startswith("x-")}),
        )

    if isinstance(resp, JSONResponse) and resp.status_code == 200:
        try:
            data = json.loads(bytes(resp.body))
        except Exception:
            return resp
        anthropic_resp = convert_response_openai_to_anthropic(data, model)
        return JSONResponse(
            status_code=200,
            content=anthropic_resp,
            headers=ascii_safe_headers({k: v for k, v in resp.headers.items() if k.lower().startswith("x-")}),
        )
    return resp

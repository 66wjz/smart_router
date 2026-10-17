"""
v1 Responses 入站接口 - POST /v1/responses（CH-010）
Responses 格式请求（Codex 等客户端）→ 内部统一 openai chat 格式 → RouterService 全链路 → 响应转回 Responses 格式
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.router_service import RouterService
from app.upstream.responses_adapter import (
    OpenaiToResponsesSSE,
    convert_request_responses_to_openai,
    convert_response_openai_to_responses,
)

log = logging.getLogger("router")

router = APIRouter(tags=["v1-responses"])


def _responses_error(status_code: int, message: str) -> JSONResponse:
    """构造 Responses 协议错误响应（Codex 等客户端依赖该格式解析错误）"""
    etype = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        429: "rate_limit_error",
        503: "api_error",
    }.get(status_code, "api_error")
    return JSONResponse(status_code=status_code, content={
        "error": {"message": message, "type": etype, "code": etype},
    })


@router.post("/v1/responses")
async def responses(request: Request):
    """Responses 兼容接口：Codex 等 Responses 协议客户端可调任意上游模型"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={
            "error": {"message": "请求体不是合法 JSON", "type": "invalid_request_error"},
        })
    if not body.get("model"):
        return JSONResponse(status_code=400, content={
            "error": {"message": "model 参数缺失", "type": "invalid_request_error"},
        })

    model = body["model"]
    openai_body = convert_request_responses_to_openai(body)
    key_groups = getattr(request.state, "key_groups", None)
    svc: RouterService = request.app.state.router_service
    log.info(f"[/v1/responses] {model} stream={bool(body.get('stream'))} key={getattr(request.state, 'key_name', '')}")

    try:
        resp = await svc.chat_completions(openai_body, key_groups, protocol="responses")
    except HTTPException as e:
        return _responses_error(e.status_code, str(e.detail) if e.detail else "上游服务不可用")

    if isinstance(resp, StreamingResponse):
        converter = OpenaiToResponsesSSE(model)

        async def responses_stream():
            try:
                async for chunk in resp.body_iterator:
                    text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "ignore")
                    for ev in converter.feed(text):
                        yield ev
                for ev in converter.close():
                    yield ev
            except Exception as e:
                log.error(f"/v1/responses 流式转换中断: {e}")

        return StreamingResponse(
            responses_stream(),
            media_type="text/event-stream",
            headers={k: v for k, v in resp.headers.items() if k.lower().startswith("x-")},
        )

    if isinstance(resp, JSONResponse) and resp.status_code == 200:
        try:
            data = json.loads(bytes(resp.body))
        except Exception:
            return resp
        responses_resp = convert_response_openai_to_responses(data, model)
        return JSONResponse(
            status_code=200,
            content=responses_resp,
            headers={k: v for k, v in resp.headers.items() if k.lower().startswith("x-")},
        )
    return resp

"""
v1 聊天补全接口 - POST /v1/chat/completions
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services.router_service import RouterService

router = APIRouter(tags=["v1-chat"])


def _openai_error(status_code: int, message: str) -> JSONResponse:
    """构造 OpenAI 协议错误响应（OpenAI SDK 依赖该格式解析错误）"""
    return JSONResponse(status_code=status_code, content={
        "error": {"message": message, "type": "api_error", "code": status_code},
    })


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI 兼容聊天补全：聚合路由 / 别名转发 / 直接透传 + 失败重试"""
    body = await request.json()
    key_groups = getattr(request.state, "key_groups", None)
    svc: RouterService = request.app.state.router_service
    try:
        return await svc.chat_completions(body, key_groups)
    except HTTPException as e:
        return _openai_error(e.status_code, str(e.detail) if e.detail else "上游服务不可用")

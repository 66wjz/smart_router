"""
v1 聊天补全接口 - POST /v1/chat/completions
"""

from fastapi import APIRouter, Request

from app.services.router_service import RouterService

router = APIRouter(tags=["v1-chat"])


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI 兼容聊天补全：聚合路由 / 别名转发 / 直接透传 + 失败重试"""
    body = await request.json()
    key_groups = getattr(request.state, "key_groups", None)
    svc: RouterService = request.app.state.router_service
    return await svc.chat_completions(body, key_groups)

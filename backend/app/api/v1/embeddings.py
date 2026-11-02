"""
v1 向量（Embeddings）接口 - POST /v1/embeddings（CH-054）
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services.router_service import RouterService

router = APIRouter(tags=["v1-embeddings"])


def _openai_error(status_code: int, message: str) -> JSONResponse:
    """构造 OpenAI 协议错误响应（OpenAI SDK 依赖该格式解析错误）"""
    return JSONResponse(status_code=status_code, content={
        "error": {"message": message, "type": "api_error", "code": status_code},
    })


def _valid_input(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return False


@router.post("/v1/embeddings")
async def embeddings(request: Request):
    """OpenAI 兼容向量接口：别名 / 直连 → Key 池转发 → 失败切同模型其他源"""
    try:
        body = await request.json()
    except Exception:
        return _openai_error(400, "请求体不是合法 JSON")
    if not isinstance(body, dict):
        return _openai_error(400, "请求体必须是 JSON 对象")
    if not isinstance(body.get("model"), str) or not body.get("model"):
        return _openai_error(400, "model 参数缺失")
    if not _valid_input(body.get("input")):
        return _openai_error(400, "input 参数缺失或为空")

    key_groups = getattr(request.state, "key_groups", None)
    svc: RouterService = request.app.state.router_service
    try:
        return await svc.embeddings(body, key_groups)
    except HTTPException as e:
        return _openai_error(e.status_code, str(e.detail) if e.detail else "向量服务不可用")

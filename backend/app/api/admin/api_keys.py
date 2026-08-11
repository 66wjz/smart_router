"""
admin API Key 接口
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-api-keys"])


@router.get("/api-keys")
async def list_api_keys(request: Request, _=Depends(check_auth)):
    """API Key 列表（含完整 key 与脱敏值）"""
    svc: ConfigService = request.app.state.config_service
    return {"api_keys": svc.list_api_keys()}


@router.post("/api-keys")
async def add_api_key(req: ApiKeyCreate, request: Request, _=Depends(check_auth)):
    """添加 API Key"""
    svc: ConfigService = request.app.state.config_service
    svc.add_api_key(req.model_dump())
    return {"ok": True}


@router.put("/api-keys/{key_value:path}")
async def update_api_key(key_value: str, req: ApiKeyUpdate, request: Request, _=Depends(check_auth)):
    """更新 API Key（启用/禁用/分组）"""
    svc: ConfigService = request.app.state.config_service
    svc.update_api_key(key_value, req.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/api-keys/{key_value:path}")
async def delete_api_key(key_value: str, request: Request, _=Depends(check_auth)):
    """删除 API Key"""
    svc: ConfigService = request.app.state.config_service
    svc.delete_api_key(key_value)
    return {"ok": True}

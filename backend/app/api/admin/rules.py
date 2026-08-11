"""
admin 路由规则接口
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.schemas.rule import RulesUpdate
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-rules"])


@router.get("/rules")
async def get_rules(request: Request, _=Depends(check_auth)):
    """路由规则列表"""
    svc: ConfigService = request.app.state.config_service
    return {"rules": svc.get_rules()}


@router.put("/rules")
async def set_rules(req: RulesUpdate, request: Request, _=Depends(check_auth)):
    """保存路由规则（整体替换）"""
    svc: ConfigService = request.app.state.config_service
    svc.set_rules([r.model_dump() for r in req.rules])
    return {"ok": True}

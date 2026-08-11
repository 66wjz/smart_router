"""
admin 聚合模型名接口
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.schemas.aggregated import AggregatedNamesUpdate
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-aggregated"])


@router.get("/aggregated-names")
async def get_aggregated_names(request: Request, _=Depends(check_auth)):
    """聚合模型名列表"""
    svc: ConfigService = request.app.state.config_service
    return {"names": svc.get_aggregated_names()}


@router.put("/aggregated-names")
async def set_aggregated_names(req: AggregatedNamesUpdate, request: Request, _=Depends(check_auth)):
    """保存聚合模型名"""
    svc: ConfigService = request.app.state.config_service
    svc.set_aggregated_names(req.names)
    return {"ok": True}

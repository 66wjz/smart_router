"""
admin 系统参数接口 - 延迟探测 / 重试 / 故障转移 / 同名聚合 / 热重载
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import check_auth
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-config"])


# ---------- 延迟探测 ----------

@router.get("/config/probe")
async def get_probe_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    return svc.get_probe_config()


@router.put("/config/probe")
async def set_probe_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    svc.set_probe_config(await request.json())
    return {"ok": True}


# ---------- 重试 ----------

@router.get("/config/retry")
async def get_retry_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    return svc.get_retry_config()


@router.put("/config/retry")
async def set_retry_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    svc.set_retry_config(await request.json())
    return {"ok": True}


# ---------- 智能重试（CH-012） ----------

@router.get("/config/smart-retry")
async def get_smart_retry_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    return svc.get_smart_retry_config()


@router.put("/config/smart-retry")
async def set_smart_retry_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    svc.set_smart_retry_config(await request.json())
    return {"ok": True}


# ---------- 故障转移 ----------

@router.get("/config/failover")
async def get_failover_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    return svc.get_failover_config()


@router.put("/config/failover")
async def set_failover_config(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    svc.set_failover_config(await request.json())
    return {"ok": True}


# ---------- 同名模型自动聚合（CH-036） ----------

class AutoAggregateRequest(BaseModel):
    enabled: bool


@router.get("/config/auto-aggregate")
async def get_auto_aggregate(request: Request, _=Depends(check_auth)):
    """同名模型自动聚合开关（默认关闭）"""
    svc: ConfigService = request.app.state.config_service
    return {"enabled": svc.get_auto_aggregate()}


@router.put("/config/auto-aggregate")
async def set_auto_aggregate(req: AutoAggregateRequest, request: Request, _=Depends(check_auth)):
    """打开/关闭同名模型自动聚合

    仅影响「同名模型是否被当作聚合组」，不影响跨源兜底（多候选仍会生成）。
    """
    svc: ConfigService = request.app.state.config_service
    svc.set_auto_aggregate(req.enabled)
    return {"ok": True, "enabled": req.enabled}


# ---------- 热重载 ----------

@router.post("/reload")
async def reload_config(request: Request, _=Depends(check_auth)):
    """热重载配置（从数据库重新加载到内存）"""
    svc: ConfigService = request.app.state.config_service
    svc.reload()
    return {"ok": True, "message": "配置已重新加载"}

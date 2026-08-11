"""
admin 模型别名接口
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.schemas.pointer import PointerCreate, PointerUpdate
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-pointers"])


@router.get("/model-pointers")
async def list_pointers(request: Request, _=Depends(check_auth)):
    """模型别名列表"""
    svc: ConfigService = request.app.state.config_service
    return {"pointers": svc.list_pointers()}


@router.post("/model-pointers")
async def add_pointer(req: PointerCreate, request: Request, _=Depends(check_auth)):
    """添加模型别名"""
    svc: ConfigService = request.app.state.config_service
    svc.add_pointer(req.model_dump())
    return {"ok": True}


@router.put("/model-pointers/{name}")
async def update_pointer(name: str, req: PointerUpdate, request: Request, _=Depends(check_auth)):
    """修改别名指向"""
    svc: ConfigService = request.app.state.config_service
    svc.update_pointer(name, req.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/model-pointers/{name}")
async def delete_pointer(name: str, request: Request, _=Depends(check_auth)):
    """删除模型别名"""
    svc: ConfigService = request.app.state.config_service
    svc.delete_pointer(name)
    return {"ok": True}

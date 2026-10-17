"""
admin 同名模型聚合组接口（CH-019 二期）
让"同名自动聚合"可视化、可勾选、可排序、可启停，而不是黑盒。

- GET    /admin/api/model-groups?model=xxx   列出同名多源模型（不带 model 列出全部）
- PUT    /admin/api/model-groups?model=xxx   保存某模型的聚合配置（勾选源 + 顺序 + 启用）
- DELETE /admin/api/model-groups?model=xxx   删除人工配置，回到自动发现

模型名走 query 参数（可能含 /，路径参数无法匹配，与既有删除模型接口一致）
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.api.deps import check_auth
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-model-groups"])


class GroupSource(BaseModel):
    upstream: str
    weight: int = 1


class ModelGroupUpdate(BaseModel):
    upstreams: list[GroupSource]
    enabled: bool = True

    @field_validator("upstreams")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("至少选择一个上游源（如需关闭聚合，请保留至少一个源并传 enabled=false）")
        return v


@router.get("/model-groups")
async def list_model_groups(request: Request, model: str | None = None, _=Depends(check_auth)):
    """所有同名多源模型（含自动发现 + 人工配置状态）；传 model 则只返回该模型"""
    svc: ConfigService = request.app.state.config_service
    groups = svc.list_model_groups()
    if model:
        groups = [g for g in groups if g["model"] == model]
    return {"groups": groups}


@router.put("/model-groups")
async def save_model_group(model: str, req: ModelGroupUpdate, request: Request, _=Depends(check_auth)):
    """保存某模型的聚合配置"""
    svc: ConfigService = request.app.state.config_service
    if not model:
        raise HTTPException(400, "model 必填")
    cfg = request.app.state.config
    upstreams = [u.model_dump() for u in req.upstreams]
    for item in upstreams:
        if not cfg.get_upstream(item["upstream"]):
            raise HTTPException(404, f"上游源 {item['upstream']} 不存在")
    svc.save_model_group(model, upstreams, req.enabled)
    return {"ok": True, "model": model}


@router.delete("/model-groups")
async def delete_model_group(model: str, request: Request, _=Depends(check_auth)):
    """删除人工配置 → 该模型回到自动发现"""
    svc: ConfigService = request.app.state.config_service
    if not model:
        raise HTTPException(400, "model 必填")
    svc.delete_model_group(model)
    return {"ok": True, "model": model}

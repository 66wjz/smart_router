"""
admin 分组管理接口
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import check_auth
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-groups"])


class GroupItem(BaseModel):
    name: str
    description: str = ""


class GroupsRequest(BaseModel):
    groups: list[GroupItem]


@router.get("/groups")
async def list_groups(request: Request, _=Depends(check_auth)):
    """分组列表"""
    svc: ConfigService = request.app.state.config_service
    return {"groups": svc.get_groups()}


@router.put("/groups")
async def set_groups(req: GroupsRequest, request: Request, _=Depends(check_auth)):
    """整体保存分组列表（被上游源/API Key 引用的分组不可删除）"""
    svc: ConfigService = request.app.state.config_service
    cfg = request.app.state.config

    # 收集当前被引用的分组
    used: set[str] = set()
    for u in cfg.upstreams:
        used.add(u.get("group_name", "free"))
    for ak in cfg.api_keys:
        for g in cfg._parse_groups(ak.get("groups")):
            used.add(g)

    new_names = {g.name for g in req.groups}
    removed_used = used - new_names
    if removed_used:
        raise HTTPException(
            400,
            f"分组 {', '.join(sorted(removed_used))} 仍被上游源或 API Key 引用，请先移除引用再删除",
        )

    svc.set_groups([{"name": g.name, "description": g.description} for g in req.groups])
    return {"ok": True}

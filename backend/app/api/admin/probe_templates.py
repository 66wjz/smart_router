"""
admin 探测模板接口（CH-023）

模板 = 一套可复用的探测节奏（间隔 / 慢阈值 / 排序 / 时段）。
多个聚合挂同一模板，改模板即全部生效；挂模板的聚合不再使用自配字段。

- GET    /admin/api/probe-templates        列表（含被引用次数与引用方）
- POST   /admin/api/probe-templates        新建
- PUT    /admin/api/probe-templates/{id}   更新
- DELETE /admin/api/probe-templates/{id}   删除（引用方 template_id 置空，回退自配）
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.api.deps import check_auth
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-probe-templates"])


class ProbeTemplateBody(BaseModel):
    name: str
    interval_seconds: int = 120
    slow_threshold_seconds: float | None = None
    sort_mode: str = "stable"
    schedule: dict = {}
    remark: str = ""

    @field_validator("name")
    @classmethod
    def _name_required(cls, v):
        if not (v or "").strip():
            raise ValueError("模板名不能为空")
        return v.strip()

    @field_validator("interval_seconds")
    @classmethod
    def _interval_min(cls, v):
        if v is None or v < 10:
            raise ValueError("探测间隔不能小于 10 秒")
        return v

    @field_validator("slow_threshold_seconds")
    @classmethod
    def _slow_min(cls, v):
        if v is None or v == 0:
            return None  # 0 = 跟随全局
        if v < 1:
            raise ValueError("慢阈值不能小于 1 秒（0 表示跟随全局）")
        return v

    @field_validator("sort_mode")
    @classmethod
    def _sort_ok(cls, v):
        if v not in ("stable", "latency"):
            raise ValueError("sort_mode 只能是 stable 或 latency")
        return v


@router.get("/probe-templates")
async def list_probe_templates(request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    return {"templates": svc.list_probe_templates()}


@router.post("/probe-templates")
async def create_probe_template(req: ProbeTemplateBody, request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    cfg = request.app.state.config
    if any(t["name"] == req.name for t in cfg.get_probe_templates()):
        raise HTTPException(400, f"模板名「{req.name}」已存在")
    tid = svc.save_probe_template(req.model_dump())
    return {"ok": True, "id": tid}


@router.put("/probe-templates/{template_id}")
async def update_probe_template(template_id: int, req: ProbeTemplateBody,
                                request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    cfg = request.app.state.config
    if not any(t["id"] == template_id for t in cfg.get_probe_templates()):
        raise HTTPException(404, f"模板 {template_id} 不存在")
    if any(t["name"] == req.name and t["id"] != template_id for t in cfg.get_probe_templates()):
        raise HTTPException(400, f"模板名「{req.name}」已存在")
    svc.save_probe_template(req.model_dump(), template_id)
    return {"ok": True, "id": template_id}


@router.delete("/probe-templates/{template_id}")
async def delete_probe_template(template_id: int, request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    cfg = request.app.state.config
    if not any(t["id"] == template_id for t in cfg.get_probe_templates()):
        raise HTTPException(404, f"模板 {template_id} 不存在")
    affected = svc.delete_probe_template(template_id)
    return {"ok": True, "id": template_id, "affected": affected}


@router.get("/probe-plan")
async def get_probe_plan(request: Request, _=Depends(check_auth)):
    """全局去重后的探测计划：单元、间隔、时段、被哪些聚合（含 rule）引用、探测成本"""
    svc: ConfigService = request.app.state.config_service
    return svc.get_probe_plan(probe=getattr(request.app.state, "probe", None))

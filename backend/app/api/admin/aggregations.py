"""
admin 统一聚合接口（CH-023）

一个实体两种形态，用 kind 区分：
  static：固定成员（原「模型聚合组」），支持异名成员
  rule  ：手写聚合名（原「聚合模型名」），候选由路由规则在运行时匹配

- GET    /admin/api/aggregations            统一列表
- PUT    /admin/api/aggregations?name=xxx   新建/更新（部分字段缺省保持原值）
- DELETE /admin/api/aggregations?name=xxx   删除
- GET    /admin/api/aggregations/rule-units rule 聚合的探测对象（候选并集，供前端预览）
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.api.deps import check_auth
from app.services.config_service import ConfigService

router = APIRouter(prefix="/admin/api", tags=["admin-aggregations"])


class AggregationMember(BaseModel):
    upstream: str
    # 该上游源里的真实模型名；为空表示与聚合名同名
    model: str | None = None
    weight: int = 1


class AggregationUpdate(BaseModel):
    kind: str | None = None                 # 新建必填；更新时缺省保持原类型
    members: list[AggregationMember] | None = None
    enabled: bool | None = None

    # 探测（若挂了模板，以下自配字段不生效）
    probe_enabled: bool | None = None
    template_id: int | None = None
    sort_mode: str | None = None
    interval_seconds: int | None = None
    slow_threshold_seconds: float | None = None
    schedule: dict | None = None
    remark: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_ok(cls, v):
        if v is not None and v not in ("static", "rule"):
            raise ValueError("kind 只能是 static 或 rule")
        return v

    @field_validator("sort_mode")
    @classmethod
    def _sort_ok(cls, v):
        if v is not None and v not in ("stable", "latency"):
            raise ValueError("sort_mode 只能是 stable 或 latency")
        return v

    @field_validator("interval_seconds")
    @classmethod
    def _interval_min(cls, v):
        if v is None or v == 0:
            return None  # 0 = 跟随全局
        if v < 10:
            raise ValueError("探测间隔不能小于 10 秒（0 表示跟随全局）")
        return v

    @field_validator("slow_threshold_seconds")
    @classmethod
    def _slow_min(cls, v):
        if v is None or v == 0:
            return None
        if v < 1:
            raise ValueError("慢阈值不能小于 1 秒（0 表示跟随全局）")
        return v


@router.get("/aggregations")
async def list_aggregations(request: Request, _=Depends(check_auth)):
    """统一聚合列表（static + rule），含生效探测参数与模板名"""
    svc: ConfigService = request.app.state.config_service
    return {"aggregations": svc.list_aggregations()}


@router.put("/aggregations")
async def save_aggregation(name: str, req: AggregationUpdate, request: Request, _=Depends(check_auth)):
    """新建或更新聚合；未提供的字段沿用库里的原值

    注意：template_id / interval_seconds / slow_threshold_seconds 需要区分
    「字段未提供」（保持原值）与「显式传 null」（清空）。用 model_fields_set 判断，
    否则前端解绑模板、清空自配间隔时会静默失效。
    """
    if not name:
        raise HTTPException(400, "name 必填")
    cfg = request.app.state.config
    svc: ConfigService = request.app.state.config_service

    existing = cfg.get_aggregations().get(name) or {}
    provided = req.model_fields_set
    kind = req.kind or existing.get("kind")
    if not kind:
        raise HTTPException(400, "新建聚合必须指定 kind（static 或 rule）")

    members = existing.get("members") or []
    if req.members is not None:
        if kind == "rule":
            raise HTTPException(400, "rule 类型聚合的候选由路由规则决定，不能配置成员")
        if not req.members:
            raise HTTPException(400, "至少选择一个成员（如需关闭聚合，请保留成员并传 enabled=false）")
        for item in req.members:
            if not cfg.get_upstream(item.upstream):
                raise HTTPException(404, f"上游源 {item.upstream} 不存在")
        members = [m.model_dump() for m in req.members]

    def pick(field: str, default=None):
        """字段显式提供（含 null）就用请求值，否则沿用原值"""
        if field in provided:
            return getattr(req, field)
        return existing.get(field, default)

    payload = {
        "kind": kind,
        "members": members,
        "enabled": req.enabled if req.enabled is not None else existing.get("enabled", True),
        "probe_enabled": req.probe_enabled if req.probe_enabled is not None
        else existing.get("probe_enabled", False),
        "template_id": pick("template_id"),
        "sort_mode": req.sort_mode or existing.get("sort_mode") or "stable",
        "interval_seconds": pick("interval_seconds"),
        "slow_threshold_seconds": pick("slow_threshold_seconds"),
        "schedule": req.schedule if req.schedule is not None else existing.get("schedule") or {},
        "remark": req.remark if req.remark is not None else existing.get("remark") or "",
    }
    if payload["template_id"] is not None:
        valid_ids = {t["id"] for t in cfg.get_probe_templates()}
        if payload["template_id"] not in valid_ids:
            raise HTTPException(404, f"探测模板 {payload['template_id']} 不存在")

    svc.save_aggregation(name, payload)
    return {"ok": True, "name": name, "kind": kind}


@router.delete("/aggregations")
async def delete_aggregation(name: str, request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    if not name:
        raise HTTPException(400, "name 必填")
    svc.delete_aggregation(name)
    return {"ok": True, "name": name}


@router.get("/aggregations/rule-units")
async def list_rule_units(request: Request, _=Depends(check_auth)):
    """rule 聚合的探测对象 = 所有路由规则候选的并集（实时展开为源 + 真实模型名）"""
    cfg = request.app.state.config
    units = cfg.rule_candidate_units()
    for u in units:
        upstream = cfg.get_upstream(u["upstream"]) or {}
        u["upstream_name"] = upstream.get("name", u["upstream"])
    return {"units": units}

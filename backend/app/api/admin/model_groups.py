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
    # 该上游源里的真实模型名；为空表示与聚合名同名（纯同名聚合）
    model: str | None = None
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


# ------------------------------------------------------------
# 归一化建议：把不同前缀/大小写/分隔符的同一模型识别为一组
# ------------------------------------------------------------

def _normalize_model_name(name: str) -> str:
    """归一化：去掉 `provider/` 前缀，统一小写，把 . _ 视作 -，压缩多余分隔符
    例：buddy/deepseek-v4.1-flash / loomy/DeepSeek-V4.1-Flash / trae/deepseek-v4.1-flash
        → deepseek-v4-1-flash
    """
    base = (name or "").strip().split("/")[-1]
    base = base.lower().replace(".", "-").replace("_", "-")
    while "--" in base:
        base = base.replace("--", "-")
    return base.strip("-")


@router.get("/model-groups/suggestions")
async def suggest_model_groups(request: Request, _=Depends(check_auth)):
    """扫描所有上游模型，按归一化名聚类，返回"疑似同一模型"的建议组
    只返回分布在 >=2 个源、且当前尚未人工配置的分组，供用户一次性确认合并。"""
    cfg = request.app.state.config
    configured = cfg.get_model_groups()

    # 归一化名 → [{upstream, upstream_name, model}]
    buckets: dict[str, list[dict]] = {}
    for u in cfg.upstreams:
        uid = u.get("upstream_id", "")
        if not cfg.is_upstream_enabled(uid):
            continue
        for m in u.get("models") or []:
            name = m.get("name") if isinstance(m, dict) else str(m)
            if not name or not cfg.is_model_enabled(uid, name):
                continue
            key = _normalize_model_name(name)
            if not key:
                continue
            buckets.setdefault(key, []).append({
                "upstream": uid,
                "upstream_name": u.get("name", uid),
                "model": name,
            })

    suggestions = []
    for key, members in buckets.items():
        upstreams_in_group = {m["upstream"] for m in members}
        if len(upstreams_in_group) < 2:
            continue
        distinct_models = {m["model"] for m in members}
        # 完全同名的不算"异名建议"，交给自动发现即可
        if len(distinct_models) < 2:
            continue
        # 已经人工配置过的（任一成员名作为聚合名）就跳过
        if any(name in configured for name in distinct_models) or key in configured:
            continue
        suggestions.append({
            "suggested_name": key,
            "normalized": key,
            "members": members,
        })

    suggestions.sort(key=lambda s: (-len(s["members"]), s["suggested_name"]))
    return {"suggestions": suggestions}


@router.get("/model-groups/source-models")
async def list_source_models(request: Request, upstream: str, _=Depends(check_auth)):
    """某上游源的已配置模型（供"添加异名成员"时下拉选择）"""
    cfg = request.app.state.config
    upstream_obj = cfg.get_upstream(upstream)
    if not upstream_obj:
        raise HTTPException(404, f"上游源 {upstream} 不存在")
    models = [
        {"name": m.get("name"), "enabled": bool(m.get("enabled", True))}
        for m in (upstream_obj.get("models") or [])
        if isinstance(m, dict) and m.get("name")
    ]
    return {"upstream": upstream, "models": models}

"""
admin 上游源接口
"""

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.deps import check_auth
from app.schemas.upstream import UpstreamCreate, UpstreamModelsRequest, UpstreamTestRequest, UpstreamUpdate
from app.services.config_service import ConfigService
from app.upstream import test_non_stream, test_non_stream_anthropic, test_non_stream_responses
from app.upstream.openai_adapter import _build_endpoint

router = APIRouter(prefix="/admin/api", tags=["admin-upstreams"])


@router.get("/upstreams")
async def list_upstreams(request: Request, _=Depends(check_auth)):
    """上游源列表（密钥脱敏）"""
    svc: ConfigService = request.app.state.config_service
    return {"upstreams": svc.list_upstreams()}


@router.post("/upstreams")
async def add_upstream(req: UpstreamCreate, request: Request, _=Depends(check_auth)):
    """添加上游源"""
    svc: ConfigService = request.app.state.config_service
    svc.add_upstream(req.model_dump())
    return {"ok": True}


@router.put("/upstreams/{upstream_id}")
async def update_upstream(upstream_id: str, req: UpstreamUpdate, request: Request, _=Depends(check_auth)):
    """更新上游源（支持启用/禁用等字段）"""
    svc: ConfigService = request.app.state.config_service
    svc.update_upstream(upstream_id, req.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/upstreams/{upstream_id}")
async def delete_upstream(upstream_id: str, request: Request, _=Depends(check_auth)):
    """删除上游源"""
    svc: ConfigService = request.app.state.config_service
    svc.delete_upstream(upstream_id)
    return {"ok": True}


@router.get("/upstreams/{upstream_id}/models")
async def fetch_upstream_models(upstream_id: str, request: Request, _=Depends(check_auth)):
    """从上游源拉取模型列表（后端代理，避免前端跨域）"""
    cfg = request.app.state.config
    http_client: httpx.AsyncClient = request.app.state.http_client
    upstream = cfg.get_upstream(upstream_id)
    if not upstream:
        return {"models": []}
    base_url = upstream.get("base_url", "").rstrip("/")
    keys = cfg.get_upstream_keys(upstream_id)
    if not base_url or not keys:
        return {"models": []}
    api_key = cfg.key_pool.pick(upstream_id, keys)
    if not api_key:
        return {"models": []}
    try:
        resp = await http_client.get(
            _build_endpoint(base_url, "/v1/models"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        data = resp.json()
        models = sorted(m.get("id", "") for m in data.get("data", []))
    except Exception:
        models = []
    return {"models": models}


@router.put("/upstreams/{upstream_id}/models")
async def set_upstream_models(upstream_id: str, req: UpstreamModelsRequest, request: Request, _=Depends(check_auth)):
    """整体写入上游源的已配置模型列表（批量加入：前端合并去重后提交）"""
    svc: ConfigService = request.app.state.config_service
    if not request.app.state.config.get_upstream(upstream_id):
        raise HTTPException(404, "上游源不存在")
    models = [m.model_dump(exclude_none=True) for m in req.models]
    svc.update_upstream(upstream_id, {"models": models})
    return {"ok": True, "models": models}


@router.delete("/upstreams/{upstream_id}/models")
async def delete_upstream_model(upstream_id: str, model: str, request: Request, _=Depends(check_auth)):
    """删除上游源已配置模型列表中的单个模型
    模型名走 query 参数（模型名可能含 /，路径参数无法匹配）"""
    svc: ConfigService = request.app.state.config_service
    cfg = request.app.state.config
    upstream = cfg.get_upstream(upstream_id)
    if not upstream:
        raise HTTPException(404, "上游源不存在")
    if not model:
        raise HTTPException(400, "model 参数必填")
    models = [m for m in (upstream.get("models") or []) if m.get("name") != model]
    svc.update_upstream(upstream_id, {"models": models})
    return {"ok": True}


@router.post("/upstreams/{upstream_id}/test")
async def test_upstream(upstream_id: str, req: UpstreamTestRequest, request: Request, _=Depends(check_auth)):
    """测试上游源的指定模型（走 Key 池选 Key，返回模型回复或具体失败原因）"""
    cfg = request.app.state.config
    http_client: httpx.AsyncClient = request.app.state.http_client
    upstream = cfg.get_upstream(upstream_id)
    if not upstream:
        raise HTTPException(404, "上游源不存在")
    if not cfg.is_upstream_enabled(upstream_id):
        raise HTTPException(400, f"上游源 {upstream_id} 已禁用，无法测试")

    body = {
        "model": req.model,
        "messages": [{"role": "user", "content": req.prompt}],
        "max_tokens": 256,
    }
    timeout = cfg.retry_config.get("response_timeout", 12)
    fmt = cfg.get_model_protocol(upstream_id, req.model)
    if fmt == "anthropic":
        content, error = await test_non_stream_anthropic(req.model, upstream_id, body, timeout, http_client, cfg)
    elif fmt == "responses":
        content, error = await test_non_stream_responses(req.model, upstream_id, body, timeout, http_client, cfg)
    else:
        content, error = await test_non_stream(req.model, upstream_id, body, timeout, http_client, cfg)
    if error:
        return JSONResponse(
            status_code=502,
            content={"ok": False, "error": f"模型 {req.model} 测试失败：{error}"},
        )
    return {"ok": True, "content": content}

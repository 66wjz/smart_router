"""
v1 模型列表接口 - GET /v1/models
返回该 Key 有权访问的"已配置模型"（上游源 models 列表）+ 聚合模型条目 + 别名条目。
不实时代理拉取上游目录——配置了哪些模型，客户端就看到哪些（CH-008 设计 / FB-015 修复确认）。
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["v1-models"])


@router.get("/v1/models")
async def list_models(request: Request):
    """返回已配置模型（按 API Key 分组过滤 + 上游启用过滤）+ 聚合模型条目 + 别名条目"""
    cfg = request.app.state.config
    key_groups = getattr(request.state, "key_groups", None)

    model_ids: set[str] = set()
    for u in cfg.upstreams:
        uid = u.get("upstream_id", "")
        if not cfg.is_upstream_enabled(uid):
            continue
        if key_groups is not None and cfg.get_upstream_groups(uid).isdisjoint(key_groups):
            continue
        for m in u.get("models") or []:
            name = m.get("name") if isinstance(m, dict) else str(m)
            # CH-019：模型级禁用不出现在客户端模型列表
            if name and cfg.is_model_enabled(uid, name):
                model_ids.add(name)

    data = [
        {"id": mid, "object": "model", "created": 0, "owned_by": "smart-router"}
        for mid in sorted(model_ids)
    ]
    result = {"object": "list", "data": data}

    # 别名条目
    for pointer in cfg.model_pointers:
        pname = pointer.get("name", "")
        if pname:
            entry = {
                "id": pname,
                "object": "model",
                "created": 0,
                "owned_by": "smart-router",
                "type": "pointer",
                "target_model": pointer.get("target_model", ""),
            }
            result["data"].insert(0, entry)

    # 聚合模型条目
    for agg_name in cfg.aggregated_names:
        ctx_values, output_values = [], []
        for rule in cfg.rules:
            for c in rule.get("candidates", []):
                mc, mo = c.get("max_context"), c.get("max_output")
                if mc:
                    ctx_values.append(mc)
                if mo:
                    output_values.append(mo)
        entry = {
            "id": agg_name,
            "object": "model",
            "created": 0,
            "owned_by": "smart-router",
            "context_length": min(ctx_values) if ctx_values else None,
            "max_output": max(output_values) if output_values else None,
        }
        result["data"].insert(0, entry)

    return JSONResponse(status_code=200, content=result)

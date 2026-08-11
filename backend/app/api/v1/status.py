"""
v1 状态接口 - GET /health、GET /status
"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["v1-status"])


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "5.0"}


@router.get("/status")
async def status(request: Request):
    """实时路由状态面板（无需鉴权）"""
    cfg = request.app.state.config
    probe = request.app.state.probe
    health = request.app.state.health

    latency_panel = probe.get_panel()
    rules_status = []
    for rule in cfg.rules:
        candidates_info = []
        for c in rule["candidates"]:
            base_w = c.get("weight", 1)
            dyn_w = probe.get_dynamic_weight(c["model"], base_w)
            candidates_info.append({
                "model": c["model"],
                "upstream": c.get("upstream", cfg.default_upstream),
                "base_weight": base_w,
                "dynamic_weight": dyn_w,
                "latency": probe.data.get(c["model"], {}).get("latency"),
                "status": probe.data.get(c["model"], {}).get("status", "unknown"),
                "max_context": c.get("max_context"),
                "max_output": c.get("max_output"),
            })
        rules_status.append({"name": rule["name"], "candidates": candidates_info})

    return {
        "version": "5.0",
        "aggregated_models": list(cfg.aggregated_names),
        "latency_panel": latency_panel,
        "rules": rules_status,
        "health": health.get_status(),
    }

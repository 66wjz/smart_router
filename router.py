"""
Smart Router v4 - AI模型智能路由代理
架构：
  core/      配置、路由引擎、探测、健康、上下文
  upstream/  OpenAI/Anthropic 适配器
  admin/     管理后台 API + 鉴权
  admin.html 管理后台前端
"""

import asyncio
import logging
import os
import sys

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根目录在 path 中
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.config import config
from core.context import estimate_tokens, has_image, has_new_image
from core.health import ModelHealth
from core.probe import LatencyProbe
from core.router_engine import get_ordered_candidates, route_request
from admin.api import admin_router
from upstream.anthropic_adapter import (
    try_non_stream_anthropic,
    try_stream_anthropic,
)
from upstream.openai_adapter import try_non_stream, try_stream
from upstream.responses_adapter import (
    convert_responses_request_to_chat,
    try_non_stream_responses,
    try_stream_responses,
)
from upstream.vision_pipeline import process_vision_pipeline

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("router")

# ============================================================
# 初始化核心组件
# ============================================================
failover_cfg = config.failover_config
health = ModelHealth(
    max_fails=failover_cfg.get("max_fails", 3),
    cooldown_seconds=failover_cfg.get("cooldown_seconds", 120),
)
probe = LatencyProbe(config)
HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0), verify=False)

# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(title="Smart Router", version="4.0")

# 挂载管理后台 API
app.include_router(admin_router)

# 把 probe/health/config 注入 app.state 供 admin API 使用
app.state.probe = probe
app.state.health = health
app.state.http_client = HTTP_CLIENT
app.state.config = config


# ============================================================
# 中间件：API Key 校验 + 分组注入
# ============================================================
@app.middleware("http")
async def require_api_key(request: Request, call_next):
    path = request.url.path
    if path.startswith("/v1/"):
        auth = request.headers.get("Authorization", "").strip()
        if not auth:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Missing API key.", "type": "auth_error", "code": 401}},
            )
        # 提取 Bearer 后面的 key
        raw_key = auth[7:] if auth.lower().startswith("bearer ") else auth
        key_entry = config.validate_api_key(raw_key)
        if not key_entry:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Invalid API key.", "type": "auth_error", "code": 401}},
            )
        # 注入 key 的分组信息，后续路由用
        request.state.key_groups = set(key_entry.get("groups", ["free"]))
        request.state.key_name = key_entry.get("name", "")
    return await call_next(request)


# ============================================================
# 启动/关闭
# ============================================================
@app.on_event("startup")
async def startup():
    asyncio.create_task(probe.run_loop(HTTP_CLIENT))
    log.info(f"Smart Router v4 启动，监听端口 {config.listen_port}")


@app.on_event("shutdown")
async def shutdown():
    probe.stop()
    await HTTP_CLIENT.aclose()


# ============================================================
# 管理后台页面（重定向到 Streamlit 管理后台 10003 端口）
# ============================================================


@app.get("/admin")
async def admin_page(request: Request):
    # 使用请求的 host 动态拼接，避免硬编码 IP
    host = request.headers.get("host", f"8.137.195.192:{config.listen_port + 1}")
    scheme = "https" if request.url.scheme == "https" else "http"
    return RedirectResponse(url=f"{scheme}://{host}")


# ============================================================
# 主路由：/v1/chat/completions
# ============================================================
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    original_model = body.get("model", "")
    is_stream = body.get("stream", False)
    request_headers = dict(request.headers)
    key_groups = getattr(request.state, "key_groups", None)

    # ========== 模型别名匹配：直接转发，不走路由规则 ==========
    pointer = config.get_model_pointer(original_model)
    if pointer:
        target = pointer.get("target_model", original_model)
        upstream_id = pointer.get("upstream", config.default_upstream)
        # 分组检查
        upstream_group = config.get_upstream_group(upstream_id)
        if key_groups is not None and upstream_group not in key_groups:
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 '{upstream_group}'（模型 {target}）",
            )
        if config.log_routing:
            log.info(f"别名转发: {original_model} → {target} (upstream={upstream_id})")
        # 替换模型名后直接透传
        body["model"] = target
        candidates = [{"model": target, "upstream": upstream_id, "max_output": None}]
    elif original_model in config.aggregated_names:
        messages = body.get("messages", [])
        est_tokens = estimate_tokens(messages)
        candidates = get_ordered_candidates(
            messages, body, config, probe, health, est_tokens,
            allowed_groups=key_groups,
        )
        if config.log_routing:
            c_str = ", ".join(c["model"].split("/")[-1] for c in candidates[:3])
            ctx_info = f" (~{est_tokens}tokens)" if est_tokens > 0 else ""
            log.info(f"路由: {original_model} → 候选 [{c_str}]{ctx_info}")
    else:
        # 直接请求特定模型名：从路由规则中查找对应的 upstream
        upstream_id = config.find_model_upstream(original_model)
        # 分组检查
        upstream_group = config.get_upstream_group(upstream_id)
        if key_groups is not None and upstream_group not in key_groups:
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 '{upstream_group}'（模型 {original_model}）",
            )
        candidates = [
            {
                "model": original_model,
                "upstream": upstream_id,
                "max_output": None,
            }
        ]
        if config.log_routing:
            log.info(f"直接转发: {original_model} → upstream={upstream_id}")

    if not candidates:
        raise HTTPException(status_code=503, detail="无可用模型")

    # ========== 视觉预处理管道（别名/直接转发路径）==========
    # 仅在下述条件全部满足时触发：
    #   1. 请求含图片
    #   2. 目标上游源配置了 vision_pipeline
    #   3. 非聚合路由（聚合路由有自己的视觉理解规则）
    is_aggregated = original_model in config.aggregated_names
    if has_image(body.get("messages", [])) and not is_aggregated:
        first_upstream = candidates[0].get("upstream", config.default_upstream)
        vp_config = config.get_vision_pipeline(first_upstream)
        if vp_config and vp_config.get("enabled"):
            if config.log_routing:
                log.info(f"[视觉管道] 检测到图片，启动视觉预处理 (upstream={first_upstream})")
            body = await process_vision_pipeline(
                body, first_upstream, config, HTTP_CLIENT
            )

    retry_cfg = config.retry_config
    max_attempts = min(retry_cfg.get("max_attempts", 3), len(candidates))
    response_timeout = retry_cfg.get("response_timeout", 60)
    first_chunk_timeout = retry_cfg.get("first_chunk_timeout", 30)

    tried = []
    for i in range(max_attempts):
        cand = candidates[i]
        model = cand["model"]
        upstream_id = cand.get("upstream", config.default_upstream)
        model_max_output = cand.get("max_output")
        tried.append(model)

        if i > 0 and config.log_routing:
            log.info(
                f"重试({i+1}/{max_attempts}): "
                f"{candidates[i-1]['model'].split('/')[-1]} 失败 → 尝试 {model.split('/')[-1]}"
            )

        # 根据上游格式选择适配器
        upstream = config.get_upstream(upstream_id)
        fmt = upstream.get("format", "openai") if upstream else "openai"

        if fmt == "anthropic":
            if is_stream:
                result = await try_stream_anthropic(
                    model, upstream_id, body, request_headers,
                    first_chunk_timeout, HTTP_CLIENT, config, health, model_max_output,
                )
            else:
                result = await try_non_stream_anthropic(
                    model, upstream_id, body, request_headers,
                    response_timeout, HTTP_CLIENT, config, health, model_max_output,
                )
        else:
            if is_stream:
                result = await try_stream(
                    model, upstream_id, body, request_headers,
                    first_chunk_timeout, HTTP_CLIENT, config, health, model_max_output,
                )
            else:
                result = await try_non_stream(
                    model, upstream_id, body, request_headers,
                    response_timeout, HTTP_CLIENT, config, health, model_max_output,
                )

        if result is not None:
            if i > 0 and config.log_routing:
                log.info(f"重试成功: {candidates[i-1]['model'].split('/')[-1]} → {model.split('/')[-1]}")
            return result

    raise HTTPException(
        status_code=503,
        detail=f"所有模型均不可用 (尝试了: {', '.join(m.split('/')[-1] for m in tried)})",
    )


# ============================================================
# 主路由：/v1/responses (codex CLI 兼容)
# 接收 Responses API 请求，内部转为 chat/completions 转发，
# 再把响应转回 Responses 格式返回。
# ============================================================
@app.post("/v1/responses")
async def responses_api(request: Request):
    body = await request.json()
    original_model = body.get("model", "")
    is_stream = body.get("stream", False)
    key_groups = getattr(request.state, "key_groups", None)

    # ========== 模型路由（复用 chat/completions 的路由逻辑） ==========
    candidates = []

    # 模型别名匹配：直接转发
    pointer = config.get_model_pointer(original_model)
    if pointer:
        target = pointer.get("target_model", original_model)
        upstream_id = pointer.get("upstream", config.default_upstream)
        upstream_group = config.get_upstream_group(upstream_id)
        if key_groups is not None and upstream_group not in key_groups:
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 '{upstream_group}'（模型 {target}）",
            )
        if config.log_routing:
            log.info(f"[Responses] 别名转发: {original_model} → {target} (upstream={upstream_id})")
        body["model"] = target
        candidates = [{"model": target, "upstream": upstream_id, "max_output": None}]

    elif original_model in config.aggregated_names:
        # 聚合路由：从转换后的 messages 估算 tokens
        chat_body = convert_responses_request_to_chat(body)
        messages = chat_body.get("messages", [])
        est_tokens = estimate_tokens(messages)
        candidates = get_ordered_candidates(
            messages, chat_body, config, probe, health, est_tokens,
            allowed_groups=key_groups,
        )
        if config.log_routing:
            c_str = ", ".join(c["model"].split("/")[-1] for c in candidates[:3])
            ctx_info = f" (~{est_tokens}tokens)" if est_tokens > 0 else ""
            log.info(f"[Responses] 路由: {original_model} → 候选 [{c_str}]{ctx_info}")

    else:
        # 直接请求特定模型名
        upstream_id = config.find_model_upstream(original_model)
        upstream_group = config.get_upstream_group(upstream_id)
        if key_groups is not None and upstream_group not in key_groups:
            raise HTTPException(
                status_code=403,
                detail=f"API Key 无权访问分组 '{upstream_group}'（模型 {original_model}）",
            )
        candidates = [{"model": original_model, "upstream": upstream_id, "max_output": None}]
        if config.log_routing:
            log.info(f"[Responses] 直接转发: {original_model} → upstream={upstream_id}")

    if not candidates:
        raise HTTPException(status_code=503, detail="无可用模型")

    # ========== 视觉预处理管道（别名/直接转发路径）==========
    # Responses 请求先转成 chat 格式检测图片，处理后再继续 Responses 适配流程
    is_aggregated = original_model in config.aggregated_names
    if not is_aggregated:
        chat_body_for_check = convert_responses_request_to_chat(body)
        if has_image(chat_body_for_check.get("messages", [])):
            first_upstream = candidates[0].get("upstream", config.default_upstream)
            vp_config = config.get_vision_pipeline(first_upstream)
            if vp_config and vp_config.get("enabled"):
                if config.log_routing:
                    log.info(f"[Responses][视觉管道] 检测到图片，启动视觉预处理 (upstream={first_upstream})")
                # 对转换后的 chat_body 跑管道，再把改造后的 messages 塞回 Responses body
                processed_chat_body = await process_vision_pipeline(
                    chat_body_for_check, first_upstream, config, HTTP_CLIENT
                )
                # 将处理后的 messages 同步回原始 Responses body
                # Responses 格式中 input 里的图片在转换后变成了 messages，
                # 我们用处理后的 messages 替换 input 相关字段
                body["_vision_processed_messages"] = processed_chat_body.get("messages", [])

    # ========== 重试逻辑 ==========
    retry_cfg = config.retry_config
    max_attempts = min(retry_cfg.get("max_attempts", 3), len(candidates))
    response_timeout = retry_cfg.get("response_timeout", 60)
    first_chunk_timeout = retry_cfg.get("first_chunk_timeout", 30)

    tried = []
    for i in range(max_attempts):
        cand = candidates[i]
        model = cand["model"]
        upstream_id = cand.get("upstream", config.default_upstream)
        model_max_output = cand.get("max_output")
        tried.append(model)

        if i > 0 and config.log_routing:
            log.info(
                f"[Responses] 重试({i+1}/{max_attempts}): "
                f"{candidates[i-1]['model'].split('/')[-1]} 失败 → 尝试 {model.split('/')[-1]}"
            )

        # Responses 端点只走 OpenAI 格式上游（chat/completions 转换）
        if is_stream:
            result = await try_stream_responses(
                model, upstream_id, body,
                first_chunk_timeout, HTTP_CLIENT, config, health, model_max_output,
            )
        else:
            result = await try_non_stream_responses(
                model, upstream_id, body,
                response_timeout, HTTP_CLIENT, config, health, model_max_output,
            )

        if result is not None:
            if i > 0 and config.log_routing:
                log.info(
                    f"[Responses] 重试成功: "
                    f"{candidates[i-1]['model'].split('/')[-1]} → {model.split('/')[-1]}"
                )
            return result

    raise HTTPException(
        status_code=503,
        detail=f"所有模型均不可用 (尝试了: {', '.join(m.split('/')[-1] for m in tried)})",
    )


# ============================================================
# /v1/models
# ============================================================
@app.get("/v1/models")
async def list_models(request: Request):
    try:
        # 使用 upstream 自带的 Key，不透传客户端 Key
        upstream = config.get_upstream(config.default_upstream)
        base_url = upstream.get("base_url", "").rstrip("/")
        api_key = upstream.get("api_key", "")
        resp = await HTTP_CLIENT.get(
            f"{base_url}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        upstream_data = resp.json()
    except Exception as e:
        upstream_data = {"object": "list", "data": []}

    # 模型别名也加入 /v1/models 列表
    model_limits = config.get_all_candidates_with_limits()
    for pointer in config.model_pointers:
        pname = pointer.get("name", "")
        if pname:
            agg_entry = {
                "id": pname,
                "object": "model",
                "created": 0,
                "owned_by": "smart-router",
                "type": "pointer",
                "target_model": pointer.get("target_model", ""),
            }
            if "data" in upstream_data:
                upstream_data["data"].insert(0, agg_entry)

    for agg_name in config.aggregated_names:
        ctx_values = []
        output_values = []
        for rule in config.rules:
            for c in rule.get("candidates", []):
                mc = c.get("max_context")
                mo = c.get("max_output")
                if mc:
                    ctx_values.append(mc)
                if mo:
                    output_values.append(mo)

        agg_entry = {
            "id": agg_name,
            "object": "model",
            "created": 0,
            "owned_by": "smart-router",
            "context_length": min(ctx_values) if ctx_values else None,
            "max_output": max(output_values) if output_values else None,
        }
        if "data" in upstream_data:
            upstream_data["data"].insert(0, agg_entry)

    return JSONResponse(status_code=200, content=upstream_data)


# ============================================================
# 健康检查 & 状态
# ============================================================
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "4.0"}


@app.get("/status")
async def status():
    """公开状态接口（无需鉴权）"""
    latency_panel = probe.get_panel()
    rules_status = []
    for rule in config.rules:
        candidates_info = []
        for c in rule["candidates"]:
            base_w = c.get("weight", 1)
            dyn_w = probe.get_dynamic_weight(c["model"], base_w)
            candidates_info.append({
                "model": c["model"],
                "upstream": c.get("upstream", config.default_upstream),
                "base_weight": base_w,
                "dynamic_weight": dyn_w,
                "latency": probe.data.get(c["model"], {}).get("latency"),
                "status": probe.data.get(c["model"], {}).get("status", "unknown"),
                "max_context": c.get("max_context"),
                "max_output": c.get("max_output"),
            })
        rules_status.append({
            "name": rule["name"],
            "candidates": candidates_info,
        })

    return {
        "version": "4.0",
        "aggregated_models": list(config.aggregated_names),
        "latency_panel": latency_panel,
        "rules": rules_status,
        "health": health.get_status(),
    }


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.listen_port)

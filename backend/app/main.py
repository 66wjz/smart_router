"""
Smart Router v5 主入口
组装：FastAPI 应用 + 中间件鉴权 + 各服务注册 + 启动探测
"""

import asyncio
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin_router, v1_router
from app.core.config import config
from app.core.health import ModelHealth
from app.core.logging_setup import (
    RequestContextMiddleware,
    describe_request,
    setup_file_logging,
)
from app.core.probe import LatencyProbe
from app.core.security import get_jwt_secret
from app.core.usage import UsageBuffer, current_api_key_id, current_api_key_name
from app.services.auth_service import AuthService
from app.services.config_service import ConfigService
from app.services.dashboard_service import DashboardService
from app.services.router_service import RouterService

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# 先 basicConfig 建控制台 handler，再挂文件 handler
# （反过来会让 basicConfig 因 root 已有 handler 而静默失效）
setup_file_logging()
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
usage_buffer = UsageBuffer(retention_days=int(config._settings.get("usage_retention_days", 30)))
HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0), verify=False)

# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(title="Smart Router", version="5.2.0")

# 挂载路由
app.include_router(v1_router)
app.include_router(admin_router)


# ============================================================
# 全局异常兜底（CH-025）
# 未捕获异常不再返回裸 500 纯文本 —— 按入站协议路径返回规范化错误体，
# 客户端（OpenAI / Anthropic / Responses SDK）才能解析出具体原因。
# ============================================================
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    ctx = describe_request(request)
    path = request.url.path
    log.error(f"未捕获异常 | {request.method} {path} | {ctx}", exc_info=exc)

    if path.startswith("/v1/messages"):
        return JSONResponse(status_code=500, content={
            "type": "error",
            "error": {"type": "api_error", "message": f"中转站内部错误: {type(exc).__name__}"},
        })
    if path.startswith("/v1/responses"):
        return JSONResponse(status_code=500, content={
            "error": {"message": f"中转站内部错误: {type(exc).__name__}", "type": "api_error"},
        })
    if path.startswith("/v1/"):
        return JSONResponse(status_code=500, content={
            "error": {"message": f"中转站内部错误: {type(exc).__name__}",
                      "type": "api_error", "code": 500},
        })
    return JSONResponse(status_code=500, content={"detail": "内部错误，请查看服务端日志"})


# 生产模式静态托管：前端构建产物 frontend_dist 存在时启用（SPA fallback）
DIST_DIR = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parent.parent.parent / "frontend_dist"))
if DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        target = (DIST_DIR / full_path).resolve()
        if full_path and target.is_file() and str(target).startswith(str(DIST_DIR.resolve())):
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")

# 注册服务到 app.state（供路由层依赖注入）
app.state.config = config
app.state.probe = probe
app.state.health = health
app.state.http_client = HTTP_CLIENT
app.state.usage_buffer = usage_buffer
app.state.router_service = RouterService(config, probe, health, HTTP_CLIENT, usage_buffer)
app.state.config_service = ConfigService(config)
app.state.auth_service = AuthService(config)
app.state.dashboard_service = DashboardService(config, probe, health)


# ============================================================
# 中间件：客户端 API Key 校验 + 分组注入 + 用量 Key 贯穿
# ============================================================
@app.middleware("http")
async def require_api_key(request: Request, call_next):
    path = request.url.path
    if path.startswith("/v1/"):
        auth = request.headers.get("Authorization", "").strip()
        if not auth:
            # Anthropic SDK 默认用 x-api-key 头鉴权（CH-009）
            auth = request.headers.get("x-api-key", "").strip()
        if not auth:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Missing API key.", "type": "auth_error", "code": 401}},
            )
        raw_key = auth[7:] if auth.lower().startswith("bearer ") else auth
        key_entry = config.validate_api_key(raw_key)
        if not key_entry:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Invalid API key.", "type": "auth_error", "code": 401}},
            )
        request.state.key_groups = set(key_entry.get("groups", ["free"]))
        request.state.key_name = key_entry.get("name", "")
        # CH-019：Key 信息贯穿到转发层（用量归属）
        api_key_id = None
        for ak in config.api_keys:
            if ak.get("key_value") == raw_key:
                api_key_id = ak.get("id")
                break
        current_api_key_id.set(api_key_id)
        current_api_key_name.set(key_entry.get("name", ""))
    return await call_next(request)


# CH-025：请求上下文中间件（缓存 /v1 请求体 + 访问日志）
# 放在 require_api_key 之后注册 → 位于更外层，401 被拦截的请求也能记到上下文
app.add_middleware(RequestContextMiddleware)


# ============================================================
# 启动 / 关闭
# ============================================================
@app.on_event("startup")
async def startup():
    # 启动即建 log_usage 表（幂等），再启动用量采集后台线程
    try:
        from app.core.database import get_conn
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "sql", "06_用量统计与自动聚合.sql"), encoding="utf-8") as f:
            get_conn().executescript(f.read())
    except Exception as e:
        log.warning(f"log_usage 表初始化失败（稍后写入时再建）: {e}")
    # CH-021：聚合探测配置表 + log_usage.upstream_model 列（幂等补齐）
    try:
        config.sync_probe_config_table()
        # CH-023：统一聚合实体 + 探测模板（幂等建表 + 旧表迁移）
        config.sync_unified_tables()
        config.load()
        from app.repositories.usage_repo import UsageRepository
        UsageRepository()._ensure_unit_column()
    except Exception as e:
        log.warning(f"CH-021/CH-023 增量结构补齐失败: {e}")
    usage_buffer.start_worker()
    probe._init_models()
    asyncio.create_task(probe.run_loop(HTTP_CLIENT))
    # CH-032：预热 JWT 密钥（环境变量 > sys_setting > 自动生成并落库）
    # 放在配置加载之后，确保 sys_setting 已就绪
    get_jwt_secret()
    log.info(f"Smart Router v5.2.0 启动，监听端口 {config.listen_port}")


@app.on_event("shutdown")
async def shutdown():
    probe.stop()
    await HTTP_CLIENT.aclose()

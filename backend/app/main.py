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
from app.core.probe import LatencyProbe
from app.core.security import JWT_SECRET
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
        config.load()
        from app.repositories.usage_repo import UsageRepository
        UsageRepository()._ensure_unit_column()
    except Exception as e:
        log.warning(f"CH-021 增量结构补齐失败: {e}")
    usage_buffer.start_worker()
    probe._init_models()
    asyncio.create_task(probe.run_loop(HTTP_CLIENT))
    log.info(f"Smart Router v5.2.0 启动，监听端口 {config.listen_port}")


@app.on_event("shutdown")
async def shutdown():
    probe.stop()
    await HTTP_CLIENT.aclose()

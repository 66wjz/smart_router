"""
管理后台 API - 鉴权 + 配置 CRUD
供 Streamlit 管理后台和 router.py 挂载使用
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger("router")

admin_router = APIRouter(prefix="/admin/api")


# ============================================================
# JWT 工具
# ============================================================
JWT_SECRET = "smart-router-jwt-secret-2026"
JWT_ALG = "HS256"


def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_jwt(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": JWT_ALG, "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_jwt(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        signing_input = f"{header}.{body}".encode()
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ============================================================
# 鉴权依赖
# ============================================================
def _get_config(request: Request):
    return request.app.state.config


def _check_auth(request: Request) -> dict:
    """验证 JWT，返回 payload 或抛 401"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    payload = verify_jwt(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return payload


# ============================================================
# 登录
# ============================================================
@admin_router.post("/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    cfg = _get_config(request)
    admin_cfg = cfg.admin_config
    if username != admin_cfg.get("username", "admin") or password != admin_cfg.get("password", "smart-router-2026"):
        raise HTTPException(401, "用户名或密码错误")
    hours = admin_cfg.get("session_hours", 24)
    token = create_jwt({"sub": username, "exp": int(time.time()) + hours * 3600, "iat": int(time.time())})
    return {"ok": True, "token": token}


# ============================================================
# 热重载
# ============================================================
@admin_router.post("/reload")
async def reload_config(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    cfg.reload()
    return {"ok": True, "message": "配置已重新加载"}


# ============================================================
# 仪表盘
# ============================================================
@admin_router.get("/dashboard")
async def dashboard(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    probe = request.app.state.probe
    health = request.app.state.health

    all_models = cfg.get_all_models()
    model_ok = sum(1 for m in all_models if probe.data.get(m, {}).get("status") == "ok")
    model_down = sum(1 for m in all_models if probe.data.get(m, {}).get("status") == "down")
    model_unknown = len(all_models) - model_ok - model_down

    return {
        "upstream_count": len(cfg.upstreams),
        "model_count": len(all_models),
        "model_ok": model_ok,
        "model_down": model_down + model_unknown,
        "rule_count": len(cfg.rules),
        "pointer_count": len(cfg.model_pointers),
        "api_key_count": len(cfg.api_keys),
        "health": health.get_status(),
    }


# ============================================================
# 上游源 CRUD
# ============================================================
@admin_router.get("/upstreams")
async def list_upstreams(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    result = []
    for u in cfg.upstreams:
        key = u.get("api_key", "")
        masked = key[:4] + "*" * (max(len(key) - 8, 0)) + key[-4:] if len(key) > 8 else "****"
        result.append({**u, "api_key": masked})
    return {"upstreams": result}


@admin_router.post("/upstreams")
async def add_upstream(request: Request):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    if not cfg.add_upstream(body):
        raise HTTPException(400, "上游源 ID 已存在")
    return {"ok": True}


@admin_router.delete("/upstreams/{upstream_id}")
async def delete_upstream(request: Request, upstream_id: str):
    _check_auth(request)
    cfg = _get_config(request)
    if not cfg.delete_upstream(upstream_id):
        raise HTTPException(404, "上游源不存在")
    return {"ok": True}


# ============================================================
# 路由规则
# ============================================================
@admin_router.get("/rules")
async def get_rules(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    return {"rules": cfg.rules}


@admin_router.put("/rules")
async def set_rules(request: Request):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    cfg.set_rules(body.get("rules", []))
    return {"ok": True}


# ============================================================
# 聚合模型名
# ============================================================
@admin_router.get("/aggregated-names")
async def get_aggregated_names(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    return {"names": list(cfg.aggregated_names)}


@admin_router.put("/aggregated-names")
async def set_aggregated_names(request: Request):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    cfg.set_aggregated_names(body.get("names", []))
    return {"ok": True}


# ============================================================
# 模型别名（指针）CRUD
# ============================================================
@admin_router.get("/model-pointers")
async def list_model_pointers(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    return {"pointers": cfg.model_pointers}


@admin_router.post("/model-pointers")
async def add_model_pointer(request: Request):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    name = body.get("name", "")
    target = body.get("target_model", "")
    upstream = body.get("upstream", cfg.default_upstream)
    if not name or not target:
        raise HTTPException(400, "name 和 target_model 为必填")
    if not cfg.add_model_pointer({"name": name, "target_model": target, "upstream": upstream}):
        raise HTTPException(400, f"别名 '{name}' 已存在")
    return {"ok": True}


@admin_router.put("/model-pointers/{name}")
async def update_model_pointer(request: Request, name: str):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    if not cfg.update_model_pointer(name, body):
        raise HTTPException(404, f"别名 '{name}' 不存在")
    return {"ok": True}


@admin_router.delete("/model-pointers/{name}")
async def delete_model_pointer(request: Request, name: str):
    _check_auth(request)
    cfg = _get_config(request)
    if not cfg.delete_model_pointer(name):
        raise HTTPException(404, f"别名 '{name}' 不存在")
    return {"ok": True}


# ============================================================
# 配置项 API
# ============================================================
@admin_router.get("/config/probe")
async def get_probe_config(request: Request):
    _check_auth(request)
    return _get_config(request).probe_config


@admin_router.put("/config/probe")
async def set_probe_config(request: Request):
    _check_auth(request)
    body = await request.json()
    _get_config(request).set_probe_config(body)
    return {"ok": True}


@admin_router.get("/config/retry")
async def get_retry_config(request: Request):
    _check_auth(request)
    return _get_config(request).retry_config


@admin_router.put("/config/retry")
async def set_retry_config(request: Request):
    _check_auth(request)
    body = await request.json()
    _get_config(request).set_retry_config(body)
    return {"ok": True}


@admin_router.get("/config/failover")
async def get_failover_config(request: Request):
    _check_auth(request)
    return _get_config(request).failover_config


@admin_router.put("/config/failover")
async def set_failover_config(request: Request):
    _check_auth(request)
    body = await request.json()
    _get_config(request).set_failover_config(body)
    return {"ok": True}


@admin_router.put("/admin-password")
async def change_admin_password(request: Request):
    _check_auth(request)
    body = await request.json()
    old_pass = body.get("old_password", "")
    new_pass = body.get("new_password", "")
    cfg = _get_config(request)
    admin_cfg = cfg.admin_config
    if old_pass != admin_cfg.get("password", "smart-router-2026"):
        raise HTTPException(400, "当前密码错误")
    admin_cfg["password"] = new_pass
    cfg.set_admin_config(admin_cfg)
    return {"ok": True}


# ============================================================
# 路由层 API Key 管理
# ============================================================
@admin_router.get("/api-keys")
async def list_api_keys(request: Request):
    _check_auth(request)
    cfg = _get_config(request)
    # 脱敏：只显示前4位和后4位
    result = []
    for ak in cfg.api_keys:
        key_val = ak.get("key", "")
        if len(key_val) > 8:
            masked = key_val[:4] + "*" * (len(key_val) - 8) + key_val[-4:]
        else:
            masked = "****"
        result.append({
            "name": ak.get("name", ""),
            "key": key_val,  # 管理后台需要完整 key
            "key_masked": masked,
            "enabled": ak.get("enabled", True),
        })
    return {"api_keys": result}


@admin_router.post("/api-keys")
async def add_api_key(request: Request):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    name = body.get("name", "")
    key_value = body.get("key", "")
    enabled = body.get("enabled", True)
    if not key_value:
        raise HTTPException(400, "key 为必填")
    if not cfg.add_api_key({"name": name, "key": key_value, "enabled": enabled}):
        raise HTTPException(400, "API Key 已存在")
    return {"ok": True}


@admin_router.put("/api-keys/{key_value:path}")
async def update_api_key(request: Request, key_value: str):
    _check_auth(request)
    body = await request.json()
    cfg = _get_config(request)
    if not cfg.update_api_key(key_value, body):
        raise HTTPException(404, "API Key 不存在")
    return {"ok": True}


@admin_router.delete("/api-keys/{key_value:path}")
async def delete_api_key(request: Request, key_value: str):
    _check_auth(request)
    cfg = _get_config(request)
    if not cfg.delete_api_key(key_value):
        raise HTTPException(404, "API Key 不存在")
    return {"ok": True}

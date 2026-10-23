"""
依赖注入 - 管理后台 JWT 鉴权
"""

from fastapi import HTTPException, Request

from app.core.security import verify_jwt
from app.services.auth_service import current_password_version


def check_auth(request: Request) -> dict:
    """验证管理接口 JWT，返回 payload 或抛 401"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    payload = verify_jwt(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    # CH-049：比对密码指纹，改密后旧 token 立即失效。
    # 默认密码走 auth_service 的同一个默认值，避免两处默认值不一致导致全量 401。
    if payload.get("pv") != current_password_version(request.app.state.config.admin_config):
        raise HTTPException(401, "密码已变更，请重新登录")
    return payload

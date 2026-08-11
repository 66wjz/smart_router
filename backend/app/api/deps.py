"""
依赖注入 - 管理后台 JWT 鉴权
"""

from fastapi import HTTPException, Request

from app.core.security import verify_jwt


def check_auth(request: Request) -> dict:
    """验证管理接口 JWT，返回 payload 或抛 401"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    payload = verify_jwt(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return payload

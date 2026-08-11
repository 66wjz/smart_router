"""
admin 认证接口 - 登录 / 修改密码
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/admin/api", tags=["admin-auth"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    """管理员登录，返回 JWT"""
    svc: AuthService = request.app.state.auth_service
    token = svc.login(req.username, req.password)
    return LoginResponse(token=token)


@router.put("/admin-password")
async def change_password(req: ChangePasswordRequest, request: Request, _=Depends(check_auth)):
    """修改管理员密码"""
    svc: AuthService = request.app.state.auth_service
    svc.change_password(req.old_password, req.new_password)
    return {"ok": True}

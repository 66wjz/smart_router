"""
认证服务 - 登录 / JWT 签发 / 修改密码
"""

import time

from fastapi import HTTPException

from app.core.config import AppConfig
from app.core.security import create_jwt


class AuthService:
    def __init__(self, config: AppConfig):
        self.config = config

    def login(self, username: str, password: str) -> str:
        """校验用户名密码，成功返回 JWT token"""
        admin_cfg = self.config.admin_config
        expected_user = admin_cfg.get("username", "admin")
        expected_pass = admin_cfg.get("password", "smart-router-2026")
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "用户名或密码错误")
        hours = admin_cfg.get("session_hours", 24)
        token = create_jwt({
            "sub": username,
            "exp": int(time.time()) + hours * 3600,
            "iat": int(time.time()),
        })
        return token

    def change_password(self, old_password: str, new_password: str) -> None:
        """修改管理员密码，旧密码错误抛 400"""
        admin_cfg = self.config.admin_config
        if old_password != admin_cfg.get("password", "smart-router-2026"):
            raise HTTPException(400, "当前密码错误")
        admin_cfg["password"] = new_password
        self.config.set_admin_config(admin_cfg)

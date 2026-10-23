"""
认证服务 - 登录 / JWT 签发 / 修改密码
"""

import hashlib
import time

from fastapi import HTTPException

from app.core.config import AppConfig
from app.core.security import create_jwt


DEFAULT_PASSWORD = "smart-router-2026"


def password_version(password: str) -> str:
    """密码指纹（CH-049）：写进 JWT 的 `pv` 字段，改密后旧 token 自动失效。

    为什么用密码指纹而不是随机版本号：
        版本号要额外落库（多一个 sys_setting 键），改密时忘记递增就失效不了；
        指纹从密码本身推导，密码一变指纹必然变，不存在忘记递增的可能。
    只取 sha256 前 16 位，且仅在签名后的 payload 内出现，不额外暴露密码信息。
    """
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()[:16]


def current_password_version(admin_cfg: dict) -> str:
    """当前生效密码的指纹。

    CH-049：默认密码必须只有一处定义 —— 否则 login 用 `smart-router-2026`
    推导 pv，check_auth 用 `""` 推导，两者不等会让所有请求 401
    （sys_setting 里还没有 admin 记录时就会踩到，例如全新库/回归脚本）。
    """
    return password_version(admin_cfg.get("password", DEFAULT_PASSWORD))


def make_admin_token(admin_cfg: dict, username: str = "admin", hours: int = 1) -> str:
    """按当前配置签发一个管理端 token（测试/脚本用，含 pv 指纹）。"""
    return create_jwt({
        "sub": username,
        "pv": current_password_version(admin_cfg),
        "exp": int(time.time()) + hours * 3600,
        "iat": int(time.time()),
    })


class AuthService:
    def __init__(self, config: AppConfig):
        self.config = config

    def login(self, username: str, password: str) -> str:
        """校验用户名密码，成功返回 JWT token"""
        admin_cfg = self.config.admin_config
        expected_user = admin_cfg.get("username", "admin")
        expected_pass = admin_cfg.get("password", DEFAULT_PASSWORD)
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "用户名或密码错误")
        hours = admin_cfg.get("session_hours", 24)
        token = create_jwt({
            "sub": username,
            # CH-049：带上密码指纹，改密后旧 token 被 deps.check_auth 拒绝
            "pv": password_version(expected_pass),
            "exp": int(time.time()) + hours * 3600,
            "iat": int(time.time()),
        })
        return token

    def change_password(self, old_password: str, new_password: str) -> None:
        """修改管理员密码，旧密码错误抛 400"""
        admin_cfg = self.config.admin_config
        if old_password != admin_cfg.get("password", DEFAULT_PASSWORD):
            raise HTTPException(400, "当前密码错误")
        admin_cfg["password"] = new_password
        self.config.set_admin_config(admin_cfg)

"""
安全模块 - JWT 生成/验证 + 密钥获取

CH-032：JWT 签名密钥不再硬编码。
优先级：SR_JWT_SECRET 环境变量 > sys_setting.jwt_secret > 首次启动自动生成并落库。
多实例部署必须显式设置 SR_JWT_SECRET，否则各实例密钥不同、token 互不认可。
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from typing import Optional

JWT_ALG = "HS256"
SETTING_KEY = "jwt_secret"
ENV_KEY = "SR_JWT_SECRET"

log = logging.getLogger("router")

_secret_lock = threading.Lock()
_secret_cache: Optional[str] = None


def _read_from_db() -> Optional[str]:
    """从 sys_setting 读取密钥；表不存在或值为空时返回 None"""
    try:
        from app.repositories.setting_repo import SettingRepository

        value = SettingRepository().get(SETTING_KEY)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as e:  # 表不存在 / 数据库不可用
        log.warning(f"读取 {SETTING_KEY} 失败，将走降级逻辑: {e}")
    return None


def _write_to_db(secret: str) -> bool:
    """把密钥写入 sys_setting；失败返回 False"""
    try:
        from app.repositories.setting_repo import SettingRepository

        SettingRepository().set(SETTING_KEY, secret)
        return True
    except Exception as e:
        log.warning(f"写入 {SETTING_KEY} 失败: {e}")
        return False


def _resolve_secret() -> str:
    env_secret = (os.environ.get(ENV_KEY) or "").strip()
    if env_secret:
        return env_secret

    db_secret = _read_from_db()
    if db_secret:
        return db_secret

    generated = secrets.token_urlsafe(48)
    if _write_to_db(generated):
        log.info(f"已自动生成 JWT 密钥并写入 sys_setting.{SETTING_KEY}（如需轮换请改该值后重启）")
    else:
        log.warning("JWT 密钥无法持久化，本次使用进程内随机密钥（重启后所有会话失效）")
    return generated


def get_jwt_secret() -> str:
    """获取 JWT 签名密钥（进程内缓存，线程安全）"""
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    with _secret_lock:
        if _secret_cache is None:
            _secret_cache = _resolve_secret()
        return _secret_cache


def reset_cache() -> None:
    """清空进程内缓存（测试用：模拟重启 / 密钥轮换）"""
    global _secret_cache
    with _secret_lock:
        _secret_cache = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_jwt(payload: dict) -> str:
    """生成 JWT token"""
    header = _b64url(json.dumps({"alg": JWT_ALG, "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    sig = hmac.new(get_jwt_secret().encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_jwt(token: str) -> Optional[dict]:
    """验证 JWT，返回 payload 或 None"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        signing_input = f"{header}.{body}".encode()
        expected_sig = hmac.new(get_jwt_secret().encode(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

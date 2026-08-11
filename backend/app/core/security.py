"""
安全模块 - JWT 生成/验证
从 v4 admin/api.py 迁移，接口保持一致。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

JWT_SECRET = "smart-router-jwt-secret-2026"
JWT_ALG = "HS256"


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
    sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_jwt(token: str) -> Optional[dict]:
    """验证 JWT，返回 payload 或 None"""
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

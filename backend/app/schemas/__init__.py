"""
Schema 包 - Pydantic 入参出参定义
"""

from app.schemas.auth import LoginRequest, LoginResponse, ChangePasswordRequest
from app.schemas.upstream import UpstreamCreate, UpstreamUpdate
from app.schemas.rule import RulesUpdate
from app.schemas.pointer import PointerCreate, PointerUpdate
from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate
from app.schemas.aggregated import AggregatedNamesUpdate

__all__ = [
    "LoginRequest", "LoginResponse", "ChangePasswordRequest",
    "UpstreamCreate", "UpstreamUpdate",
    "RulesUpdate",
    "PointerCreate", "PointerUpdate",
    "ApiKeyCreate", "ApiKeyUpdate",
    "AggregatedNamesUpdate",
]

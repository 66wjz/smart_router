"""
API 路由包
"""

from app.api.v1.router import v1_router
from app.api.admin.router import admin_router

__all__ = ["v1_router", "admin_router"]

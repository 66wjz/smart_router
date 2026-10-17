"""
admin 路由聚合
"""

from fastapi import APIRouter

from app.api.admin.auth import router as auth_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.upstreams import router as upstreams_router
from app.api.admin.rules import router as rules_router
from app.api.admin.pointers import router as pointers_router
from app.api.admin.api_keys import router as api_keys_router
from app.api.admin.aggregated import router as aggregated_router
from app.api.admin.aggregations import router as aggregations_router
from app.api.admin.probe_templates import router as probe_templates_router
from app.api.admin.config import router as config_router
from app.api.admin.groups import router as groups_router
from app.api.admin.model_groups import router as model_groups_router
from app.api.admin.usage import router as usage_router

admin_router = APIRouter()
admin_router.include_router(auth_router)
admin_router.include_router(dashboard_router)
admin_router.include_router(upstreams_router)
admin_router.include_router(rules_router)
admin_router.include_router(pointers_router)
admin_router.include_router(api_keys_router)
admin_router.include_router(aggregated_router)
admin_router.include_router(aggregations_router)
admin_router.include_router(probe_templates_router)
admin_router.include_router(config_router)
admin_router.include_router(groups_router)
admin_router.include_router(model_groups_router)
admin_router.include_router(usage_router)

__all__ = ["admin_router"]

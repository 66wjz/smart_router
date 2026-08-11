"""
v1 路由聚合
"""

from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.messages import router as messages_router
from app.api.v1.models import router as models_router
from app.api.v1.responses import router as responses_router
from app.api.v1.status import router as status_router

v1_router = APIRouter()
v1_router.include_router(chat_router)
v1_router.include_router(messages_router)
v1_router.include_router(responses_router)
v1_router.include_router(models_router)
v1_router.include_router(status_router)

__all__ = ["v1_router"]

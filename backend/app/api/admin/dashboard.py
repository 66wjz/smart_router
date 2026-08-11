"""
admin 仪表盘接口 - GET /admin/api/dashboard
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/admin/api", tags=["admin-dashboard"])


@router.get("/dashboard")
async def dashboard(request: Request, _=Depends(check_auth)):
    """仪表盘聚合数据"""
    svc: DashboardService = request.app.state.dashboard_service
    return svc.get_dashboard()

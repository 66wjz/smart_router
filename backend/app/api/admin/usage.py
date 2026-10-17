"""
admin 用量统计接口（CH-019）
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.core.usage import UsageBuffer

router = APIRouter(prefix="/admin/api", tags=["admin-usage"])


def _repo():
    from app.repositories.usage_repo import UsageRepository
    return UsageRepository()


@router.get("/usage/summary")
async def usage_summary(request: Request, range: str = "today", _=Depends(check_auth)):
    """全局汇总：总请求 / 总 tokens / 成功率 / 活跃 Key 数 / 错误 Top"""
    return _repo().summary(range)


@router.get("/usage/by-model")
async def usage_by_model(request: Request, range: str = "7d", _=Depends(check_auth)):
    """模型级聚合（按 tokens 降序）"""
    return {"models": _repo().by_model(range)}


@router.get("/usage/by-key")
async def usage_by_key(request: Request, range: str = "7d", _=Depends(check_auth)):
    """Key 级聚合（按 tokens 降序）"""
    return {"keys": _repo().by_key(range)}


@router.get("/usage/logs")
async def usage_logs(request: Request, range: str = "today", page: int = 1, size: int = 50,
                     key_id: int | None = None, model: str | None = None, status: str | None = None,
                     _=Depends(check_auth)):
    """请求明细分页"""
    return _repo().logs(range, page, size, key_id, model, status)


@router.post("/usage/flush")
async def usage_flush(request: Request, _=Depends(check_auth)):
    """手动触发缓冲落库（调试/收尾用）"""
    buffer: UsageBuffer = request.app.state.usage_buffer
    buffer.flush()
    return {"ok": True}

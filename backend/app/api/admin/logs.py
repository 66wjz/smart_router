"""
admin 运行日志查看接口（CH-025）

只读暴露轮转日志文件尾部，便于不 SSH 也能拿到出错现场。
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_auth
from app.core.logging_setup import log_file, tail_logs

router = APIRouter(prefix="/admin/api", tags=["admin-logs"])


@router.get("/logs")
async def read_logs(request: Request, lines: int = 200, keyword: str = "",
                    _=Depends(check_auth)):
    """读取服务端日志尾部（最多 5000 行，可按关键词过滤）"""
    data = tail_logs(lines=lines, keyword=keyword)
    data["ok"] = True
    return data


@router.get("/logs/info")
async def logs_info(request: Request, _=Depends(check_auth)):
    """日志文件路径与大小"""
    path = log_file()
    return {
        "ok": True,
        "file": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
    }

"""
admin 用量统计接口（CH-019）
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

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


@router.get("/usage/by-unit")
async def usage_by_unit(request: Request, range: str = "7d", _=Depends(check_auth)):
    """按「上游源 × 上游真实模型名」聚合（号池消耗核算，CH-021）"""
    return {"units": _repo().by_unit(range)}


@router.get("/usage/by-key")
async def usage_by_key(request: Request, range: str = "7d", _=Depends(check_auth)):
    """Key 级聚合（按 tokens 降序）"""
    return {"keys": _repo().by_key(range)}


@router.get("/usage/logs")
async def usage_logs(request: Request, range: str = "today", page: int = 1, size: int = 50,
                     key_id: int | None = None, model: str | None = None, status: str | None = None,
                     _=Depends(check_auth)):
    """请求明细分页

    CH-038：行内补 cache_read_tokens / cache_write_tokens / attempt_count（旧库缺列时为 0/1）
    """
    data = _repo().logs(range, page, size, key_id, model, status)
    for row in data.get("items", []):
        row.setdefault("cache_read_tokens", 0)
        row.setdefault("cache_write_tokens", 0)
        row.setdefault("attempt_count", 1)
    return data


@router.get("/usage/logs/{log_id}")
async def usage_log_detail(log_id: int, request: Request, _=Depends(check_auth)):
    """单条请求详情（CH-038）

    返回 summary（主表行）+ attempts（尝试链）+ detail（三栏报文，可能不可用）。
    """
    from fastapi import HTTPException

    repo = _repo()
    got = repo.get_detail(log_id)
    if not got:
        raise HTTPException(404, f"请求记录 {log_id} 不存在")

    summary = got["summary"]
    detail_row = got["detail"]

    attempts = []
    if detail_row and detail_row.get("attempts"):
        try:
            import json as _json
            attempts = _json.loads(detail_row["attempts"])
        except Exception:
            attempts = []

    detail = {"available": False, "reason": "该请求未采集详情报文（可能早于详情功能上线，或采集策略为 off）"}
    if detail_row:
        truncated = {}
        for key in ("request_body", "forward_body", "response_body"):
            val = detail_row.get(key)
            truncated[key] = bool(val and "…[truncated " in val)
        headers = {}
        if detail_row.get("request_headers"):
            try:
                import json as _json
                headers = _json.loads(detail_row["request_headers"])
            except Exception:
                headers = {}
        detail = {
            "available": True,
            "request_headers": headers,
            "request_body": detail_row.get("request_body"),
            "forward_body": detail_row.get("forward_body"),
            "response_body": detail_row.get("response_body"),
            "truncated": truncated,
        }

    summary.setdefault("cache_read_tokens", 0)
    summary.setdefault("cache_write_tokens", 0)
    summary.setdefault("attempt_count", 1)
    return {"id": log_id, "summary": summary, "attempts": attempts, "detail": detail}


# ---------- 详情采集策略（CH-038） ----------

class UsageDetailSetting(BaseModel):
    mode: str
    max_bytes: int | None = None
    retention_days: int | None = None


@router.get("/config/usage-detail")
async def get_usage_detail_config(request: Request, _=Depends(check_auth)):
    """读取详情采集策略"""
    cfg = request.app.state.config
    raw = cfg._settings
    mode = str(raw.get("usage_detail_mode") or "error_only")
    if mode not in ("off", "error_only", "all"):
        mode = "error_only"
    try:
        max_bytes = int(raw.get("usage_detail_max_bytes") or 1048576)
    except (TypeError, ValueError):
        max_bytes = 1048576
    try:
        retention = int(raw.get("usage_retention_days") or 14)
    except (TypeError, ValueError):
        retention = 14
    return {"mode": mode, "max_bytes": max_bytes, "retention_days": retention}


@router.put("/config/usage-detail")
async def set_usage_detail_config(req: UsageDetailSetting, request: Request, _=Depends(check_auth)):
    """保存详情采集策略

    - mode: off / error_only / all
    - max_bytes: 1024 ~ 1048576（1MB 上限，防止误配成极大值）
    - retention_days 通过同一入口一并保存（前端可一起提交）
    """
    from fastapi import HTTPException

    if req.mode not in ("off", "error_only", "all"):
        raise HTTPException(422, "mode 只能是 off / error_only / all")

    cfg = request.app.state.config
    cfg.set_setting("usage_detail_mode", req.mode)

    if req.max_bytes is not None:
        if not (1024 <= req.max_bytes <= 1048576):
            raise HTTPException(422, "max_bytes 必须在 1024 ~ 1048576 之间")
        cfg.set_setting("usage_detail_max_bytes", req.max_bytes)

    retention = req.retention_days
    if retention is not None:
        if not (1 <= retention <= 3650):
            raise HTTPException(422, "retention_days 必须在 1 ~ 3650 之间")
        cfg.set_setting("usage_retention_days", retention)

    return {"ok": True}


@router.post("/usage/flush")
async def usage_flush(request: Request, _=Depends(check_auth)):
    """手动触发缓冲落库（调试/收尾用）"""
    buffer: UsageBuffer = request.app.state.usage_buffer
    buffer.flush()
    return {"ok": True}

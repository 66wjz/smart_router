"""admin 数据导出接口（CH-042）

设计：一个通用端点 + 一组「数据集」，不为每个列表单独写一套导出逻辑。

    GET  /admin/api/export/{dataset}              导出全部
    POST /admin/api/export/{dataset}              批量导出（body 传 ids）

为什么用 POST 传 ids 而不是 GET 带 query：
    批量导出可能选中上百条，拼进 URL 会超长；POST body 没这个限制，
    而且语义上「导出这批指定的记录」也更像一次查询提交。

为什么不在前端生成 xlsx：
    用户明确要求「导出就导出全部」——30 天用量动辄上万条，前端只能拿到当前页。
    后端导出才能一次查全量。
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import check_auth
from app.core.xlsx_writer import build_xlsx, export_filename

router = APIRouter(prefix="/admin/api", tags=["admin-export"])


class BatchExportBody(BaseModel):
    """批量导出：只导出选中的记录"""
    ids: list[str] = Field(default_factory=list)


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    # filename* 按 RFC 5987 编码，中文名在浏览器里才不会变成乱码
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                f"attachment; filename=export.xlsx; filename*=UTF-8''{quote(filename)}",
            # 前端 axios 要读这个头才能拿到真实文件名
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ---------------------------------------------------------------- 数据集定义
# 每个数据集返回 (列定义, 全部行)。列定义 = [(表头, 取值函数)]，
# 取值函数接收原始行，返回要写进单元格的值 —— 让「数据整形」集中在一处。

def _dataset_pointers(request: Request):
    svc = request.app.state.config_service
    rows = svc.list_pointers()

    # 支持与页面一致的筛选（导出「你看到的这批」而不是无视条件全导）
    keyword = (request.query_params.get("keyword") or "").strip().lower()
    upstream = (request.query_params.get("upstream") or "").strip()
    if keyword:
        rows = [
            r for r in rows
            if keyword in str(r.get("name") or "").lower()
            or keyword in str(r.get("target_model") or "").lower()
        ]
    if upstream:
        rows = [r for r in rows if (r.get("upstream") or "") == upstream]

    cols = [
        ("别名", lambda r: r.get("name")),
        ("目标模型", lambda r: r.get("target_model")),
        ("上游源", lambda r: r.get("upstream")),
    ]
    return "模型别名", cols, rows, lambda r: r.get("name")


def _dataset_api_keys(request: Request):
    svc = request.app.state.config_service
    rows = svc.list_api_keys()

    # 支持与页面一致的筛选
    keyword = (request.query_params.get("keyword") or "").strip().lower()
    group = (request.query_params.get("group") or "").strip()
    enabled = (request.query_params.get("enabled") or "").strip()
    if keyword:
        rows = [
            r for r in rows
            if keyword in str(r.get("name") or "").lower()
            or keyword in str(r.get("key") or "").lower()
        ]
    if group:
        rows = [r for r in rows if group in (r.get("groups") or [])]
    if enabled in ("0", "1"):
        want = enabled == "1"
        rows = [r for r in rows if bool(r.get("enabled")) is want]

    cols = [
        ("名称", lambda r: r.get("name")),
        # 导出给管理员存档用，保留完整 Key；页面上的脱敏展示不受影响
        ("Key", lambda r: r.get("key")),
        ("分组", lambda r: "、".join(r.get("groups") or [])),
        ("状态", lambda r: "启用" if r.get("enabled") else "禁用"),
    ]
    return "API Key", cols, rows, lambda r: r.get("name")


def _dataset_filter_rules(request: Request):
    cfg = request.app.state.config
    rows = cfg.list_filter_rules()

    # 支持与页面一致的筛选
    keyword = (request.query_params.get("keyword") or "").strip().lower()
    upstream = (request.query_params.get("upstream") or "").strip()
    enabled = (request.query_params.get("enabled") or "").strip()
    if keyword:
        rows = [
            r for r in rows
            if keyword in str(r.get("name") or "").lower()
            or keyword in str(r.get("pattern") or "").lower()
        ]
    if upstream:
        rows = [r for r in rows if upstream in (r.get("upstream_ids") or [])]
    if enabled in ("0", "1"):
        want = enabled == "1"
        rows = [r for r in rows if bool(r.get("enabled")) is want]

    target_label = {
        "system_first_line": "system 首行",
        "system_any": "任一 system 消息",
        "body_regex": "整个请求体（正则）",
    }
    action_label = {"skip": "跳过该源", "reject": "直接拒绝"}
    cols = [
        ("规则名", lambda r: r.get("name")),
        ("匹配位置", lambda r: target_label.get(r.get("target"), r.get("target"))),
        ("匹配内容", lambda r: r.get("pattern")),
        ("作用源", lambda r: "、".join(r.get("upstream_ids") or []) or "全部源"),
        ("命中动作", lambda r: action_label.get(r.get("action"), r.get("action"))),
        ("启用", lambda r: "是" if r.get("enabled") else "否"),
        ("备注", lambda r: r.get("remark")),
    ]
    return "请求过滤规则", cols, rows, lambda r: str(r.get("id"))


def _dataset_usage_by_model(request: Request):
    from app.repositories.usage_repo import UsageRepository

    range_name = request.query_params.get("range", "today")
    rows = UsageRepository().by_model(range_name)
    cols = [
        ("模型", lambda r: r.get("model")),
        ("请求数", lambda r: r.get("requests")),
        ("错误数", lambda r: r.get("error_count")),
        ("Prompt Tokens", lambda r: r.get("prompt_tokens")),
        ("Completion Tokens", lambda r: r.get("completion_tokens")),
        ("总 Tokens", lambda r: r.get("total_tokens")),
        ("平均耗时(ms)", lambda r: r.get("avg_duration_ms")),
        ("源数", lambda r: r.get("upstream_count")),
    ]
    return "用量-按模型", cols, rows, lambda r: str(r.get("model"))


def _dataset_usage_by_unit(request: Request):
    from app.repositories.usage_repo import UsageRepository

    range_name = request.query_params.get("range", "today")
    rows = UsageRepository().by_unit(range_name)
    cols = [
        ("上游源", lambda r: r.get("upstream_name") or r.get("upstream_id")),
        ("真实模型名", lambda r: r.get("upstream_model")),
        ("请求数", lambda r: r.get("requests")),
        ("错误数", lambda r: r.get("error_count")),
        ("总 Tokens", lambda r: r.get("total_tokens")),
        ("请求名数", lambda r: r.get("request_models")),
        ("平均耗时(ms)", lambda r: r.get("avg_duration_ms")),
    ]
    return "用量-按单元", cols, rows, lambda r: f"{r.get('upstream_id')}|{r.get('upstream_model')}"


def _dataset_usage_by_key(request: Request):
    from app.repositories.usage_repo import UsageRepository

    range_name = request.query_params.get("range", "today")
    rows = UsageRepository().by_key(range_name)
    cols = [
        ("Key 名称", lambda r: r.get("api_key_name") or f"#{r.get('api_key_id')}"),
        ("请求数", lambda r: r.get("requests")),
        ("错误数", lambda r: r.get("error_count")),
        ("总 Tokens", lambda r: r.get("total_tokens")),
        ("平均耗时(ms)", lambda r: r.get("avg_duration_ms")),
    ]
    return "用量-按Key", cols, rows, lambda r: str(r.get("api_key_id"))


def _dataset_usage_logs(request: Request):
    """请求明细：全量导出（分页查询逐页拉，避免一次载入过多）"""
    from app.repositories.usage_repo import UsageRepository

    range_name = request.query_params.get("range", "today")
    model = request.query_params.get("model") or None
    status = request.query_params.get("status") or None
    repo = UsageRepository()

    rows, page, page_size = [], 1, 1000
    while True:
        got = repo.logs(range_name, page, page_size, None, model, status)
        batch = got.get("items") or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
        if page > 200:      # 硬上限 20 万条，防止误点撑爆内存
            break

    cols = [
        ("时间", lambda r: (r.get("created_at") or "")[:19].replace("T", " ")),
        ("Key", lambda r: r.get("api_key_name")),
        ("模型", lambda r: r.get("model")),
        ("上游源", lambda r: r.get("upstream_name") or r.get("upstream_id")),
        ("真实模型", lambda r: r.get("upstream_model")),
        ("协议", lambda r: r.get("protocol")),
        ("流式", lambda r: "是" if r.get("stream") else "否"),
        ("状态", lambda r: r.get("status")),
        ("HTTP", lambda r: r.get("http_status")),
        ("输入 Tokens", lambda r: r.get("prompt_tokens")),
        ("缓存 Tokens", lambda r: r.get("cache_read_tokens")),
        ("输出 Tokens", lambda r: r.get("completion_tokens")),
        ("尝试次数", lambda r: r.get("attempt_count")),
        ("耗时(ms)", lambda r: r.get("duration_ms")),
        ("错误", lambda r: r.get("error_msg")),
    ]
    return "请求明细", cols, rows, lambda r: str(r.get("id"))


def _dataset_groups(request: Request):
    cfg = request.app.state.config
    rows = cfg.get_groups()
    cols = [
        ("分组名", lambda r: r.get("name")),
        ("描述", lambda r: r.get("description")),
    ]
    return "分组", cols, rows, lambda r: r.get("name")


def _dataset_probe_templates(request: Request):
    svc = request.app.state.config_service
    rows = svc.list_probe_templates()
    cols = [
        ("模板名", lambda r: r.get("name")),
        ("间隔(s)", lambda r: r.get("interval_seconds")),
        ("慢阈值(s)", lambda r: r.get("slow_threshold_seconds")),
        ("排序", lambda r: "速度优先" if r.get("sort_mode") == "latency" else "稳定优先"),
        ("被引用", lambda r: "、".join(r.get("ref_names") or [])),
        ("备注", lambda r: r.get("remark")),
    ]
    return "探测模板", cols, rows, lambda r: str(r.get("id"))


def _dataset_probe_units(request: Request):
    svc = request.app.state.config_service
    plan = request.app.state.probe
    data = svc.get_probe_plan(plan)
    rows = data.get("units") or []
    cols = [
        ("上游源", lambda r: r.get("upstream_name") or r.get("upstream")),
        ("真实模型名", lambda r: r.get("model")),
        ("引用聚合", lambda r: "、".join(r.get("groups") or [])),
        ("间隔(s)", lambda r: r.get("interval")),
        ("最近延迟(s)", lambda r: r.get("latency")),
        ("状态", lambda r: {"ok": "可用", "down": "不可用"}.get(r.get("status"), "未知")),
        ("是否在探测时段", lambda r: "是" if r.get("active_now") else "否"),
    ]
    return "探测单元", cols, rows, lambda r: f"{r.get('upstream')}|{r.get('model')}"


DATASETS = {
    "pointers": _dataset_pointers,
    "api-keys": _dataset_api_keys,
    "filter-rules": _dataset_filter_rules,
    "usage-by-model": _dataset_usage_by_model,
    "usage-by-unit": _dataset_usage_by_unit,
    "usage-by-key": _dataset_usage_by_key,
    "usage-logs": _dataset_usage_logs,
    "groups": _dataset_groups,
    "probe-templates": _dataset_probe_templates,
    "probe-units": _dataset_probe_units,
}


def _build_response(request: Request, dataset: str, ids: list[str] | None) -> StreamingResponse:
    builder = DATASETS.get(dataset)
    if builder is None:
        raise HTTPException(404, f"未知的导出数据集：{dataset}")

    sheet_name, cols, rows, id_of = builder(request)

    if ids:
        wanted = set(ids)
        rows = [r for r in rows if id_of(r) in wanted]

    headers = [c[0] for c in cols]
    data = [[c[1](r) for c in cols] for r in rows]
    content = build_xlsx(sheet_name, headers, data)
    return _xlsx_response(content, export_filename(sheet_name))


@router.get("/export/datasets")
async def list_datasets(_=Depends(check_auth)):
    """可用数据集清单（调试与文档用）

    注意：本路由必须声明在 `/export/{dataset}` **之前**，否则会被通配吃掉。
    """
    return {"datasets": sorted(DATASETS.keys())}


@router.get("/export/{dataset}")
async def export_all(dataset: str, request: Request, _=Depends(check_auth)):
    """导出全部（当前筛选条件内）"""
    return _build_response(request, dataset, None)


@router.post("/export/{dataset}")
async def export_batch(dataset: str, req: BatchExportBody, request: Request,
                       _=Depends(check_auth)):
    """批量导出：只导出 ids 里指定的记录"""
    if not req.ids:
        raise HTTPException(400, "批量导出需要至少选择一条记录")
    return _build_response(request, dataset, req.ids)

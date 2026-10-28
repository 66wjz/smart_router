"""
admin 统一聚合接口（CH-023）

一个实体两种形态，用 kind 区分：
  static：固定成员（原「模型聚合组」），支持异名成员
  rule  ：手写聚合名（原「聚合模型名」），候选由路由规则在运行时匹配

- GET    /admin/api/aggregations            统一列表
- PUT    /admin/api/aggregations?name=xxx   新建/更新（部分字段缺省保持原值）
- DELETE /admin/api/aggregations?name=xxx   删除
- GET    /admin/api/aggregations/rule-units rule 聚合的探测对象（候选并集，供前端预览）
- POST   /admin/api/aggregations/test?name=xxx 测试聚合（成员逐个 + 走聚合一次，CH-051）
"""

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.api.deps import check_auth
from app.services.config_service import ConfigService
from app.upstream import (
    test_non_stream,
    test_non_stream_anthropic,
    test_non_stream_responses,
)

router = APIRouter(prefix="/admin/api", tags=["admin-aggregations"])


class AggregationMember(BaseModel):
    upstream: str
    # 该上游源里的真实模型名；为空表示与聚合名同名
    model: str | None = None
    weight: int = 1


class AggregationUpdate(BaseModel):
    kind: str | None = None                 # 新建必填；更新时缺省保持原类型
    members: list[AggregationMember] | None = None
    # 仅 kind=rule：规则绑定子集；null / [] = 全跟随（CH-024）
    rule_bindings: list[dict] | None = None
    # CH-034：可用分组；空 = 所有 Key 可用
    groups: list[str] | None = None
    enabled: bool | None = None
    # CH-052：会话亲和；null = 跟随全局，0 = 关闭，1 = 开启
    affinity: int | None = None

    # 探测（若挂了模板，以下自配字段不生效）
    probe_enabled: bool | None = None
    template_id: int | None = None
    sort_mode: str | None = None
    interval_seconds: int | None = None
    slow_threshold_seconds: float | None = None
    schedule: dict | None = None
    remark: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_ok(cls, v):
        if v is not None and v not in ("static", "rule"):
            raise ValueError("kind 只能是 static 或 rule")
        return v

    @field_validator("sort_mode")
    @classmethod
    def _sort_ok(cls, v):
        if v is not None and v not in ("stable", "latency"):
            raise ValueError("sort_mode 只能是 stable 或 latency")
        return v

    @field_validator("interval_seconds")
    @classmethod
    def _interval_min(cls, v):
        if v is None or v == 0:
            return None  # 0 = 跟随全局
        if v < 10:
            raise ValueError("探测间隔不能小于 10 秒（0 表示跟随全局）")
        return v

    @field_validator("slow_threshold_seconds")
    @classmethod
    def _slow_min(cls, v):
        if v is None or v == 0:
            return None
        if v < 1:
            raise ValueError("慢阈值不能小于 1 秒（0 表示跟随全局）")
        return v

    @field_validator("affinity")
    @classmethod
    def _affinity_ok(cls, v):
        if v is not None and v not in (0, 1):
            raise ValueError("affinity 只能是 0、1 或 null")
        return v


def _validate_bindings(cfg, raw: list[dict] | None) -> list[dict] | None:
    """校验规则绑定（CH-024）

    - 空 / None → None（全跟随）
    - 规则名必须存在
    - 候选必须属于该规则（防止前端传错 upstream）
    """
    if not raw:
        return None
    valid_rules = {r.get("name"): r for r in cfg.rules}
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(400, "规则绑定格式不正确")
        rule_name = str(item.get("rule") or "").strip()
        if not rule_name:
            raise HTTPException(400, "规则绑定缺少 rule 名称")
        rule = valid_rules.get(rule_name)
        if rule is None:
            raise HTTPException(404, f"路由规则「{rule_name}」不存在")

        cands = item.get("candidates")
        if cands is None:
            cleaned.append({"rule": rule_name, "candidates": None})
            continue
        if not isinstance(cands, list) or not cands:
            raise HTTPException(400, f"规则「{rule_name}」至少要保留一个候选（全选请传 candidates=null）")

        available = {
            (c.get("upstream", cfg.default_upstream), c.get("model"))
            for c in rule.get("candidates", [])
        }
        picked = []
        for c in cands:
            if not isinstance(c, dict) or not c.get("upstream") or not c.get("model"):
                raise HTTPException(400, "候选项需要 upstream 与 model")
            key = (c["upstream"], c["model"])
            if key not in available:
                raise HTTPException(400, f"候选 {c['upstream']}·{c['model']} 不在规则「{rule_name}」中")
            picked.append({"upstream": c["upstream"], "model": c["model"]})
        cleaned.append({"rule": rule_name, "candidates": picked})
    if not cleaned:
        return None
    return cleaned


class AggregationOrderRequest(BaseModel):
    """聚合列表人工顺序（CH-028）"""
    names: list[str] = []


class AggregationTestRequest(BaseModel):
    """聚合测试（CH-051）：提示词 + 是否附带「走聚合一次」"""
    prompt: str = "你好，请回复一句话"
    include_aggregate: bool = True


@router.get("/aggregations")
async def list_aggregations(request: Request, _=Depends(check_auth)):
    """统一聚合列表（static + rule），含生效探测参数与模板名"""
    svc: ConfigService = request.app.state.config_service
    return {"aggregations": svc.list_aggregations()}


@router.put("/aggregations/order")
async def save_aggregation_order(req: AggregationOrderRequest, request: Request, _=Depends(check_auth)):
    """保存聚合列表的人工拖拽顺序（存 sys_setting，不改表结构）

    只保留当前真实存在的聚合名；未列出的聚合（新增/自动发现）读取时排末尾。
    """
    svc: ConfigService = request.app.state.config_service
    count = svc.save_aggregation_order(req.names)
    return {"ok": True, "count": count}


@router.put("/aggregations")
async def save_aggregation(name: str, req: AggregationUpdate, request: Request, _=Depends(check_auth)):
    """新建或更新聚合；未提供的字段沿用库里的原值

    注意：template_id / interval_seconds / slow_threshold_seconds 需要区分
    「字段未提供」（保持原值）与「显式传 null」（清空）。用 model_fields_set 判断，
    否则前端解绑模板、清空自配间隔时会静默失效。
    """
    if not name:
        raise HTTPException(400, "name 必填")
    cfg = request.app.state.config
    svc: ConfigService = request.app.state.config_service

    existing = cfg.get_aggregations().get(name) or {}
    provided = req.model_fields_set
    kind = req.kind or existing.get("kind")
    if not kind:
        raise HTTPException(400, "新建聚合必须指定 kind（static 或 rule）")

    members = existing.get("members") or []
    if req.members is not None:
        if kind == "rule":
            raise HTTPException(400, "rule 类型聚合的候选由路由规则决定，不能配置成员")
        if not req.members:
            raise HTTPException(400, "至少选择一个成员（如需关闭聚合，请保留成员并传 enabled=false）")
        for item in req.members:
            if not cfg.get_upstream(item.upstream):
                raise HTTPException(404, f"上游源 {item.upstream} 不存在")
        members = [m.model_dump() for m in req.members]

    # CH-024：规则绑定校验（仅 rule 聚合）
    rule_bindings = existing.get("rule_bindings")
    if "rule_bindings" in provided:
        if kind != "rule":
            if req.rule_bindings:
                raise HTTPException(400, "只有 rule 类型聚合可以配置规则绑定")
            rule_bindings = None
        else:
            rule_bindings = _validate_bindings(cfg, req.rule_bindings)
    elif kind == "rule" and req.kind == "rule" and not existing:
        rule_bindings = None

    def pick(field: str, default=None):
        """字段显式提供（含 null）就用请求值，否则沿用原值"""
        if field in provided:
            return getattr(req, field)
        return existing.get(field, default)

    # CH-034：可用分组（空 = 所有 Key 可用）；分组名必须真实存在
    if "groups" in provided:
        groups = [str(g) for g in (req.groups or []) if g]
        valid_groups = {g.get("name") for g in cfg.get_groups()}
        unknown = [g for g in groups if g not in valid_groups]
        if unknown:
            raise HTTPException(404, f"分组不存在: {', '.join(unknown)}")
    else:
        groups = list(existing.get("groups") or [])

    payload = {
        "kind": kind,
        "members": members,
        "rule_bindings": rule_bindings,
        "groups": groups,
        "enabled": req.enabled if req.enabled is not None else existing.get("enabled", True),
        "probe_enabled": req.probe_enabled if req.probe_enabled is not None
        else existing.get("probe_enabled", False),
        "template_id": pick("template_id"),
        "sort_mode": req.sort_mode or existing.get("sort_mode") or "stable",
        "interval_seconds": pick("interval_seconds"),
        "slow_threshold_seconds": pick("slow_threshold_seconds"),
        "schedule": req.schedule if req.schedule is not None else existing.get("schedule") or {},
        "remark": req.remark if req.remark is not None else existing.get("remark") or "",
        # CH-052：显式传 null = 恢复跟随全局
        "affinity": pick("affinity"),
    }
    if payload["template_id"] is not None:
        valid_ids = {t["id"] for t in cfg.get_probe_templates()}
        if payload["template_id"] not in valid_ids:
            raise HTTPException(404, f"探测模板 {payload['template_id']} 不存在")

    svc.save_aggregation(name, payload)
    return {"ok": True, "name": name, "kind": kind}


@router.delete("/aggregations")
async def delete_aggregation(name: str, request: Request, _=Depends(check_auth)):
    svc: ConfigService = request.app.state.config_service
    if not name:
        raise HTTPException(400, "name 必填")
    svc.delete_aggregation(name)
    return {"ok": True, "name": name}


async def _run_member_test(cfg, http_client: httpx.AsyncClient, upstream_id: str,
                           model: str, body: dict, timeout: float) -> tuple[str | None, str | None]:
    """按模型协议调一次上游（与上游源「测试」同一条路径，不写用量、不动健康状态）"""
    fmt = cfg.get_model_protocol(upstream_id, model)
    if fmt == "anthropic":
        return await test_non_stream_anthropic(model, upstream_id, body, timeout, http_client, cfg)
    if fmt == "responses":
        return await test_non_stream_responses(model, upstream_id, body, timeout, http_client, cfg)
    return await test_non_stream(model, upstream_id, body, timeout, http_client, cfg)


@router.post("/aggregations/test")
async def test_aggregation(name: str, req: AggregationTestRequest,
                           request: Request, _=Depends(check_auth)):
    """测试聚合（CH-051）

    两段结果：
    1) members：逐个成员独立打一次上游（static = 配置成员；rule = 绑定规则的候选并集，最多 20 个）
    2) aggregate：按真实路由（含权重分发/兜底顺序）试一次，返回实际命中的成员与失败尝试链

    测试请求不写用量、不改健康状态，避免「点一下测试」影响在线路由。
    """
    cfg = request.app.state.config
    http_client: httpx.AsyncClient = request.app.state.http_client
    health = request.app.state.health
    svc = request.app.state.router_service

    entity = cfg.get_aggregations().get(name)
    if not entity:
        raise HTTPException(404, f"聚合「{name}」不存在")
    if not entity.get("enabled", True):
        raise HTTPException(400, f"聚合「{name}」已关闭，无法测试")

    kind = entity.get("kind") or "static"
    prompt = (req.prompt or "").strip() or "你好，请回复一句话"
    timeout = cfg.retry_config.get("response_timeout", 12)
    target_body = {
        "model": name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
    }

    # ---------- 1) 逐个成员 ----------
    targets: list[dict] = []
    truncated = False
    if kind == "rule":
        units = cfg.rule_candidate_units(name)
        truncated = len(units) > 20
        for u in units[:20]:
            targets.append({"upstream": u["upstream"], "model": u["model"], "weight": None})
    else:
        seen: set[tuple[str, str]] = set()
        for m in entity.get("members") or []:
            uid = m.get("upstream") or ""
            model = m.get("model") or name
            if not uid or (uid, model) in seen:
                continue
            seen.add((uid, model))
            targets.append({
                "upstream": uid,
                "model": model,
                "weight": max(1, int(m.get("weight") or 1)),
            })

    enabled_targets = [
        t for t in targets
        if cfg.get_upstream(t["upstream"])
        and cfg.is_upstream_enabled(t["upstream"])
        and cfg.is_model_enabled(t["upstream"], t["model"])
    ]
    total_weight = sum(t["weight"] or 1 for t in enabled_targets) if kind == "static" else 0

    results = []
    for t in targets:
        uid, model = t["upstream"], t["model"]
        upstream = cfg.get_upstream(uid)
        if not upstream:
            results.append({**t, "status": "skipped", "error": "上游源不存在", "share": None, "cooling": False})
            continue
        if not cfg.is_upstream_enabled(uid):
            results.append({**t, "status": "skipped", "error": "上游源已禁用", "share": None, "cooling": False})
            continue
        if not cfg.is_model_enabled(uid, model):
            results.append({**t, "status": "skipped", "error": "该模型已禁用", "share": None, "cooling": False})
            continue

        share = round((t["weight"] or 1) / total_weight, 4) if total_weight else None
        start = time.time()
        content, error = await _run_member_test(cfg, http_client, uid, model, {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 64,
        }, timeout)
        results.append({
            **t,
            "share": share,
            "cooling": not health.is_available(uid, model),
            "status": "ok" if not error else "fail",
            "latency_ms": int((time.time() - start) * 1000),
            "content": (content or "")[:500] if content else None,
            "error": error,
        })

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
    }

    # ---------- 2) 走聚合一次 ----------
    aggregate = None
    if req.include_aggregate:
        candidates, mode = svc.resolve_candidates(name, dict(target_body), None)
        max_attempts = min(int(cfg.retry_config.get("max_attempts", 3) or 3), len(candidates))
        tried: list[dict] = []
        served = None
        for cand in candidates[:max_attempts]:
            uid, model = cand.get("upstream", ""), cand.get("model", "")
            start = time.time()
            content, error = await _run_member_test(cfg, http_client, uid, model, {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
            }, timeout)
            latency = int((time.time() - start) * 1000)
            tried.append({
                "upstream": uid,
                "model": model,
                "ok": not error,
                "latency_ms": latency,
                "error": error,
            })
            if not error:
                served = {"upstream": uid, "model": model, "latency_ms": latency,
                          "content": (content or "")[:500]}
                break
        aggregate = {
            "ok": served is not None,
            "mode": mode,
            "candidate_count": len(candidates),
            "candidates": [
                {"upstream": c.get("upstream"), "model": c.get("model"), "weight": c.get("weight", 1)}
                for c in candidates[:max_attempts]
            ],
            "served": served,
            "tried": tried,
            "error": None if served else "所有候选均不可用",
        }

    return {
        "ok": True,
        "name": name,
        "kind": kind,
        "prompt": prompt,
        "members": results,
        "summary": summary,
        "aggregate": aggregate,
        "truncated": truncated,
    }



@router.get("/aggregations/rule-units")
async def list_rule_units(request: Request, name: str | None = None, _=Depends(check_auth)):
    """rule 聚合的探测对象（规则候选并集）

    传 name 时只返回该聚合绑定的规则/候选展开结果（CH-024）；不传则为全部规则。
    """
    cfg = request.app.state.config
    units = cfg.rule_candidate_units(name)
    for u in units:
        upstream = cfg.get_upstream(u["upstream"]) or {}
        u["upstream_name"] = upstream.get("name", u["upstream"])
    return {"units": units, "aggregation": name}

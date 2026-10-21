"""admin 请求过滤规则接口（CH-041）

规则用于「转发前过滤」：命中规则的请求不会发到对应上游源，
避免触发上游渠道的客户端黑名单（如 WorkBuddy 拦截 DSH / Claude Code）。

- GET    /admin/api/filter-rules              规则列表 + 全局开关状态
- POST   /admin/api/filter-rules              新建
- PUT    /admin/api/filter-rules/{id}         更新
- DELETE /admin/api/filter-rules/{id}         删除
- PUT    /admin/api/filter-rules/engine       切换全局开关
- POST   /admin/api/filter-rules/test         试跑：传入请求体，返回会命中哪些规则
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.api.deps import check_auth
from app.core.filter_engine import ACTIONS, TARGETS, match_rules

router = APIRouter(prefix="/admin/api", tags=["admin-filter-rules"])


class FilterRuleBody(BaseModel):
    name: str
    enabled: bool = False
    target: str = "system_first_line"
    pattern: str
    upstream_ids: list[str] = []
    action: str = "skip"
    remark: str = ""

    @field_validator("name")
    @classmethod
    def _name_required(cls, v):
        if not (v or "").strip():
            raise ValueError("规则名不能为空")
        return v.strip()

    @field_validator("pattern")
    @classmethod
    def _pattern_required(cls, v):
        if not (v or "").strip():
            raise ValueError("匹配内容不能为空")
        return v

    @field_validator("target")
    @classmethod
    def _target_ok(cls, v):
        if v not in TARGETS:
            raise ValueError(f"匹配位置只能是 {' / '.join(TARGETS)}")
        return v

    @field_validator("action")
    @classmethod
    def _action_ok(cls, v):
        if v not in ACTIONS:
            raise ValueError(f"动作只能是 {' / '.join(ACTIONS)}")
        return v


class EngineBody(BaseModel):
    enabled: bool


class TestBody(BaseModel):
    body: dict
    upstream_ids: list[str] = []


@router.get("/filter-rules")
async def list_filter_rules(request: Request, _=Depends(check_auth)):
    cfg = request.app.state.config
    return {
        "enabled": cfg.filter_engine_enabled,
        "rules": cfg.list_filter_rules(),
        "targets": list(TARGETS),
        "actions": list(ACTIONS),
    }


@router.post("/filter-rules")
async def create_filter_rule(req: FilterRuleBody, request: Request, _=Depends(check_auth)):
    cfg = request.app.state.config
    if any(r["name"] == req.name for r in cfg.list_filter_rules()):
        raise HTTPException(400, f"规则名「{req.name}」已存在")
    new_id = cfg.save_filter_rule(req.model_dump())
    return {"ok": True, "id": new_id}


@router.put("/filter-rules/engine")
async def set_engine(req: EngineBody, request: Request, _=Depends(check_auth)):
    """切换全局开关。默认关闭，开启后所有规则才生效。"""
    cfg = request.app.state.config
    cfg.set_filter_engine_enabled(req.enabled)
    return {"ok": True, "enabled": cfg.filter_engine_enabled}


@router.put("/filter-rules/{rule_id}")
async def update_filter_rule(rule_id: int, req: FilterRuleBody,
                             request: Request, _=Depends(check_auth)):
    cfg = request.app.state.config
    rules = cfg.list_filter_rules()
    if not any(r["id"] == rule_id for r in rules):
        raise HTTPException(404, f"规则 {rule_id} 不存在")
    if any(r["name"] == req.name and r["id"] != rule_id for r in rules):
        raise HTTPException(400, f"规则名「{req.name}」已存在")
    cfg.save_filter_rule(req.model_dump(), rule_id)
    return {"ok": True, "id": rule_id}


@router.delete("/filter-rules/{rule_id}")
async def delete_filter_rule(rule_id: int, request: Request, _=Depends(check_auth)):
    cfg = request.app.state.config
    if not any(r["id"] == rule_id for r in cfg.list_filter_rules()):
        raise HTTPException(404, f"规则 {rule_id} 不存在")
    cfg.delete_filter_rule(rule_id)
    return {"ok": True, "id": rule_id}


@router.post("/filter-rules/test")
async def test_filter_rules(req: TestBody, request: Request, _=Depends(check_auth)):
    """试跑：不改变任何状态，只告诉你会命中哪些规则

    规则写错会误伤正常流量，启用前务必先用真实请求体试跑一次。
    upstream_ids 为空时，用规则自身的 upstream_ids（为空则视为作用于全部源）。
    """
    cfg = request.app.state.config
    rules = [r for r in cfg.list_filter_rules() if r.get("enabled")]

    # 未指定源时给一个占位源名，让「不限源」的规则能命中
    targets = req.upstream_ids or ["__any__"]

    results = []
    for uid in targets:
        hits = match_rules(rules, req.body, uid)
        if hits:
            results.append({
                "upstream": None if uid == "__any__" else uid,
                "rules": [{"id": r["id"], "name": r["name"], "action": r["action"]} for r in hits],
            })

    return {
        "engine_enabled": cfg.filter_engine_enabled,
        "matched": bool(results),
        "results": results,
        "enabled_rule_count": len(rules),
    }

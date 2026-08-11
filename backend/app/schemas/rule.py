"""
路由规则 Schema
"""

from pydantic import BaseModel


class Candidate(BaseModel):
    model: str
    upstream: str
    weight: int = 1
    priority: int = 1
    max_context: int | None = None
    max_output: int | None = None


class Rule(BaseModel):
    name: str
    match: dict = {}
    candidates: list[Candidate] = []


class RulesUpdate(BaseModel):
    rules: list[Rule]

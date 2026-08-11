"""
模型别名 Schema
"""

from pydantic import BaseModel


class PointerCreate(BaseModel):
    name: str
    target_model: str
    upstream: str | None = None


class PointerUpdate(BaseModel):
    target_model: str | None = None
    upstream: str | None = None

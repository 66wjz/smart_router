"""
API Key Schema
"""

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    key: str
    groups: list[str] = ["free"]
    enabled: bool = True


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    groups: list[str] | None = None
    enabled: bool | None = None

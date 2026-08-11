"""
上游源 Schema
"""

from pydantic import BaseModel, field_validator

ALLOWED_MODEL_PROTOCOLS = {"openai", "anthropic", "responses"}


class ModelEntry(BaseModel):
    name: str
    protocol: str | None = None

    @field_validator("protocol")
    @classmethod
    def _check_protocol(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_MODEL_PROTOCOLS:
            raise ValueError(f"protocol 仅支持 {sorted(ALLOWED_MODEL_PROTOCOLS)}")
        return v


class UpstreamCreate(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str | None = None
    api_keys: list[str] | None = None
    format: str = "openai"
    group: str = "free"
    groups: list[str] | None = None
    probe_enabled: bool = True
    smart_retry: bool = False
    models: list[ModelEntry] | None = None


class UpstreamUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_keys: list[str] | None = None
    format: str | None = None
    group: str | None = None
    groups: list[str] | None = None
    probe_enabled: bool | None = None
    smart_retry: bool | None = None
    enabled: bool | None = None
    models: list[ModelEntry] | None = None


class UpstreamTestRequest(BaseModel):
    model: str
    prompt: str = "你好，请回复一句话"


class UpstreamModelsRequest(BaseModel):
    models: list[ModelEntry]

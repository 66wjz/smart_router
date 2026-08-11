"""
聚合模型名 Schema
"""

from pydantic import BaseModel


class AggregatedNamesUpdate(BaseModel):
    names: list[str]

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    limit: int = 20


class SearchRequestV2(BaseModel):
    query: str
    mode: str = "balanced"  # conservative / balanced / tokenmax
    limit: int = 20
    sources: list[str] = Field(default_factory=list)  # diary/conversation/media/imported/external
    rerank: bool = True
    graph: bool = True


class SearchResult(BaseModel):
    slug: str
    title: str
    type: str
    snippet: str
    highlight: str = ""
    source: str = ""
    score: float = 0.0
    score_breakdown: dict = Field(default_factory=dict)


class HealthReport(BaseModel):
    total_pages: int = 0
    orphan_pages: list[str] = Field(default_factory=list)
    stale_pages: list[str] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class IngestRequest(BaseModel):
    directory: str


class CompileRequest(BaseModel):
    entity_tag: str


class StatsResponse(BaseModel):
    total_pages: int = 0
    pages_by_type: dict[str, int] = Field(default_factory=dict)
    total_signals: int = 0
    unprocessed_signals: int = 0
    total_versions: int = 0
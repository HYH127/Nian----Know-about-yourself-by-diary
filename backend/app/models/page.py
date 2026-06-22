from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


PAGE_TYPES = [
    "person", "concept", "self", "company", "project",
    "meeting", "media", "source", "system",
    "habit", "emotion_pattern", "value_signal", "place",
]


class TimelineEntry(BaseModel):
    timestamp: str = ""
    content: str = ""
    source_type: str = ""
    source_id: str = ""
    source: str = ""  # Enhanced source reference (e.g., diary/2026-05-10.md)


class PageInput(BaseModel):
    slug: Optional[str] = None
    type: str = "concept"
    title: str
    frontmatter: dict = Field(default_factory=dict)
    compiled_truth: str = ""
    timeline: list[TimelineEntry] = Field(default_factory=list)
    summary: str = ""
    aliases: list = Field(default_factory=list)


class PageUpdate(BaseModel):
    compiled_truth: Optional[str] = None
    timeline_append: Optional[list[TimelineEntry]] = None
    frontmatter: Optional[dict] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    aliases: Optional[list] = None


class PageLink(BaseModel):
    slug: str
    title: str
    type: str
    link_type: str = "reference"


class PageListItem(BaseModel):
    slug: str
    type: str
    title: str
    tags: list[str] = Field(default_factory=list)
    updated_at: str = ""
    created_at: str = ""


class PageDetail(BaseModel):
    slug: str
    type: str
    title: str
    frontmatter: dict = Field(default_factory=dict)
    compiled_truth: str = ""
    timeline: list[TimelineEntry] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    forward_links: list[PageLink] = Field(default_factory=list)
    back_links: list[PageLink] = Field(default_factory=list)
    version_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    summary: Optional[str] = None
    aliases: Optional[list] = None
    change_log: Optional[list] = None
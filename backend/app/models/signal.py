from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SignalInput(BaseModel):
    type: str
    sub_type: str = ""
    content: str
    evidence: str = ""
    source_type: str = ""
    source_id: str = ""


class Signal(BaseModel):
    id: int
    signal_json: dict
    entity_tags: list[str] = Field(default_factory=list)
    status: str = "unprocessed"
    source_type: str = ""
    source_id: str = ""
    created_at: str = ""
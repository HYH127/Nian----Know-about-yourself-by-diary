from pydantic import BaseModel
from typing import Optional


class TimelineEventBase(BaseModel):
    timestamp: str
    event_type: str
    summary: str
    content: str = ""
    source_type: str
    source_id: str


class TimelineEventCreate(TimelineEventBase):
    sentiment: Optional[float] = None
    emotional_keywords: Optional[str] = None
    related_contacts: Optional[str] = None
    related_events: Optional[str] = None
    related_page_slugs: Optional[str] = None
    importance_score: float = 0.5
    is_milestone: bool = False
    is_confirmed: bool = False
    confirmed_at: Optional[str] = None
    is_locked: bool = False
    locked_at: Optional[str] = None


class TimelineEvent(TimelineEventBase):
    id: str
    sentiment: Optional[float] = None
    emotional_keywords: Optional[str] = None
    related_contacts: Optional[str] = None
    related_events: Optional[str] = None
    related_page_slugs: Optional[str] = None
    importance_score: float = 0.5
    is_milestone: bool = False
    is_confirmed: bool = False
    confirmed_at: Optional[str] = None
    is_locked: bool = False
    locked_at: Optional[str] = None
    created_at: str
    model_config = {"from_attributes": True}

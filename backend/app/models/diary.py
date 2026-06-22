from pydantic import BaseModel
from typing import Optional


class DiaryBase(BaseModel):
    date: str
    content: str


class DiaryCreate(DiaryBase):
    location: Optional[str] = None
    weather: Optional[str] = None
    temperature: Optional[str] = None
    humidity: Optional[str] = None


class DiaryUpdate(BaseModel):
    content: str
    date: Optional[str] = None


class Diary(DiaryBase):
    id: str
    extracted_summary: Optional[str] = None
    extracted_tags: Optional[str] = None
    chat_message_id: Optional[str] = None
    location: Optional[str] = None
    weather: Optional[str] = None
    temperature: Optional[str] = None
    humidity: Optional[str] = None
    created_at: str
    model_config = {"from_attributes": True}


class DiarySearchResult(BaseModel):
    id: str
    date: str
    content: str
    extracted_summary: Optional[str] = None
    extracted_tags: Optional[str] = None
    location: Optional[str] = None


class DiaryDateItem(BaseModel):
    id: str
    date: str

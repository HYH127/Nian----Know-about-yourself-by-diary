from pydantic import BaseModel
from typing import Optional, List


class ProfileFragment(BaseModel):
    id: str
    content: str
    confidence: str
    evidence: List[str] = []
    frequency: int = 1
    first_seen: str = ""
    last_updated: str = ""
    is_active: bool = True
    superseded_by: Optional[str] = None
    change_narrative: Optional[str] = None
    trigger: Optional[str] = None
    behavior: Optional[str] = None
    context: Optional[str] = None
    related_entity: Optional[str] = None
    relation_type: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[str] = None


class ProfileFragmentCreate(BaseModel):
    content: str
    confidence: str = "inferred"
    evidence: List[str] = []
    trigger: Optional[str] = None
    behavior: Optional[str] = None
    context: Optional[str] = None
    related_entity: Optional[str] = None
    relation_type: Optional[str] = None
    source: Optional[str] = None

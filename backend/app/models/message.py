from pydantic import BaseModel, Field
from datetime import datetime


class MessageBase(BaseModel):
    role: str
    content: str
    mode: str = "chat"
    session_id: str


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: str
    created_at: str
    model_config = {"from_attributes": True}

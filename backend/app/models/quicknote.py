from pydantic import BaseModel
from typing import Optional


class QuickNoteCreate(BaseModel):
    content: str


class QuickNoteUpdate(BaseModel):
    content: str


class QuickNote(BaseModel):
    id: str
    content: str
    edited_at: str
    created_at: str
    processing_status: str = "pending"
    model_config = {"from_attributes": True}


class ExpenseRecordCreate(BaseModel):
    amount: float
    category: str
    description: str = ""
    note: Optional[str] = None
    expense_date: str


class ExpenseRecordUpdate(BaseModel):
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None
    expense_date: Optional[str] = None


class ExpenseRecord(BaseModel):
    id: str
    amount: float
    category: str
    description: str
    note: Optional[str] = None
    expense_date: str
    created_at: str
    model_config = {"from_attributes": True}


class ExpenseStats(BaseModel):
    total_amount: float
    category_breakdown: list[dict]
    daily_trend: list[dict]

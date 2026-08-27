from datetime import datetime
from uuid import UUID
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel
from app.schemas.common import ORM


class NoteOut(ORM):
    id: UUID
    title: str
    body: str
    tags: str
    pinned: bool
    ref_type: str
    ref_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    title: str = ""
    body: str = ""
    tags: str = ""
    pinned: bool = False
    ref_type: str = ""
    ref_id: Optional[UUID] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None
    pinned: Optional[bool] = None


class HabitCreate(BaseModel):
    title: str
    cadence: str = "daily"
    icon: str = "check"
    target_per_week: int = 7


class HabitUpdate(BaseModel):
    title: Optional[str] = None
    cadence: Optional[str] = None
    icon: Optional[str] = None
    target_per_week: Optional[int] = None
    archived: Optional[bool] = None


class FinanceCreate(BaseModel):
    amount: Decimal
    category: str = "General"
    kind: str = "expense"
    note: str = ""
    date: Optional[datetime] = None


class BudgetCreate(BaseModel):
    category: str
    monthly_limit: Decimal


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal

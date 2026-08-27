from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    detail: str = ""
    horizon: str = "short"
    category: str = "personal"
    progress: int = 0
    target_date: Optional[datetime] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    detail: Optional[str] = None
    horizon: Optional[str] = None
    category: Optional[str] = None
    progress: Optional[int] = None
    target_date: Optional[datetime] = None
    status: Optional[str] = None


class GoalLinkCreate(BaseModel):
    ref_type: str   # task|project|topic|skill|habit
    ref_id: UUID

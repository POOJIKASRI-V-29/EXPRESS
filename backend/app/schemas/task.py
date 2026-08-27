from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class TaskOut(ORM):
    id: UUID
    title: str
    category: str
    due_at: Optional[datetime]
    est_minutes: int
    priority: str
    status: str
    icon: str
    meta: str
    source: str
    postpone_count: int


class TaskCreate(BaseModel):
    title: str
    category: str = "Personal"
    due_at: Optional[datetime] = None
    est_minutes: int = 20
    priority: str = "med"
    icon: str = "tasks"
    meta: str = ""


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None


class RescheduleIn(BaseModel):
    due_at: datetime

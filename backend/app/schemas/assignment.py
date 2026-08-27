from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class AssignmentOut(ORM):
    id: UUID
    title: str
    description: str
    due_at: datetime
    est_minutes: int
    priority: str
    status: str
    course_id: Optional[UUID]


class AssignmentCreate(BaseModel):
    title: str
    course_id: Optional[UUID] = None
    description: str = ""
    due_at: datetime
    est_minutes: int = 60
    priority: str = "med"

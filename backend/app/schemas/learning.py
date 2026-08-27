from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class TopicOut(ORM):
    id: UUID
    name: str
    area: str
    state: str
    progress: int
    course_id: Optional[UUID]
    last_reviewed_at: Optional[datetime]


class TopicCreate(BaseModel):
    name: str
    area: str = "DSA"
    state: str = "not_started"
    progress: int = 0
    course_id: Optional[UUID] = None


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    area: Optional[str] = None
    state: Optional[str] = None
    progress: Optional[int] = None


class SessionCreate(BaseModel):
    minutes: int = 25
    note: str = ""
    started_at: Optional[datetime] = None


class ScheduleStudy(BaseModel):
    due_at: datetime
    minutes: int = 45


class SkillOut(ORM):
    id: UUID
    name: str
    level: int
    pct: int


class SkillCreate(BaseModel):
    name: str
    level: int = 1
    pct: int = 10


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[int] = None
    pct: Optional[int] = None

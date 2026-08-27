from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class InternshipOut(ORM):
    id: UUID
    company: str
    role: str
    status: str
    location: str
    link: str


class InternshipCreate(BaseModel):
    company: str
    role: str
    status: str = "Applied"
    location: str = ""
    link: str = ""


class InternshipUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    link: Optional[str] = None


class ApplicationCreate(BaseModel):
    internship_id: UUID
    stage: str = "applied"
    deadline: Optional[datetime] = None
    notes: str = ""


class ApplicationUpdate(BaseModel):
    stage: Optional[str] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None

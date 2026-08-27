from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    phase: str = "Alpha V1"
    stack: str = ""
    status: str = "Active"
    completion: int = 0
    priority: int = 1
    commits: int = 0
    repo_url: str = ""
    due_at: Optional[datetime] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    phase: Optional[str] = None
    stack: Optional[str] = None
    status: Optional[str] = None
    completion: Optional[int] = None
    priority: Optional[int] = None
    commits: Optional[int] = None
    repo_url: Optional[str] = None
    due_at: Optional[datetime] = None


class PhaseCreate(BaseModel):
    name: str
    order: int = 0
    done: bool = False


class ProjectTaskCreate(BaseModel):
    title: str
    due_at: Optional[datetime] = None

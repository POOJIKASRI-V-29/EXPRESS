from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class MemoryOut(ORM):
    id: UUID
    text: str
    category: str
    source: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    text: str
    category: str = "Note"


class MemoryUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    pinned: Optional[bool] = None

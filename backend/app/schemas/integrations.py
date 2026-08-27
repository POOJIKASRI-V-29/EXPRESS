from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import ORM


class IntegrationOut(ORM):
    id: UUID
    provider: str
    status: str
    scopes: str
    account_label: str
    last_sync_at: Optional[datetime]


class IntegrationConnect(BaseModel):
    account_label: str = ""
    scopes: str = ""

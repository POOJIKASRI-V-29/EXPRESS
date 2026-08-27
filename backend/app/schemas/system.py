from datetime import datetime
from uuid import UUID
from typing import Optional
from app.schemas.common import ORM


class NotificationOut(ORM):
    id: UUID
    level: str
    title: str
    kind: str
    module: str               # which module the signal points at, so the UI can route to it
    severity: int             # 1 info .. 5 critical; drives ordering
    explanation: str          # why this was raised, in the user's terms
    action_label: str         # the single most useful next step
    action_href: str          # where that step happens
    source: str               # which detector raised it
    acknowledged: bool
    resolved: bool
    created_at: datetime
    ref_id: Optional[UUID]

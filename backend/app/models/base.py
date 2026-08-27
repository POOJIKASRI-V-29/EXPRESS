import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from app.core.database import Base, GUID, UTCDateTime


def new_id():
    return uuid.uuid4()


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


def pk():
    return Column(GUID(), primary_key=True, default=new_id)


def user_fk():
    from sqlalchemy import ForeignKey
    return Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

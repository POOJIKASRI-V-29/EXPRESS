from sqlalchemy import Column, String, Boolean, DateTime, Text, Index, Integer
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    # `dedupe_key` is looked up once per candidate signal on every scan, and
    # the tray reads unacknowledged rows — both are per-user, so both indexes
    # lead with user_id. The unique constraint is what makes a scan idempotent.
    __table_args__ = (
        Index("ix_notifications_user_dedupe", "user_id", "dedupe_key", unique=True),
        Index("ix_notifications_user_active", "user_id", "acknowledged", "resolved"),
    )
    id = pk(); user_id = user_fk()
    level = Column(String, default="info")   # info|attention|action|spider_sense|critical
    title = Column(String, nullable=False)
    kind = Column(String, default="generic")  # deadline|overdue|conflict|postponed|event|attendance|budget|career|habit|revision
    dedupe_key = Column(String, index=True, default="")  # unique-per-user signal identity
    ref_type = Column(String, default="")
    ref_id = Column(GUID(), nullable=True)
    module = Column(String, default="")       # which module the signal points at
    # A signal has to justify interrupting someone: what it noticed, why that
    # matters, and the single most useful thing to do about it.
    explanation = Column(Text, default="")     # why this was raised, in the user's terms
    action_label = Column(String, default="")  # the suggested next step
    action_href = Column(String, default="")   # where that step happens
    source = Column(String, default="")        # which detector raised it
    severity = Column(Integer, default=2)      # 1 info .. 5 critical, for ordering
    acknowledged = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)


class JOCastaConversation(Base, TimestampMixin):
    __tablename__ = "jocasta_conversations"
    __table_args__ = (Index("ix_jocasta_user_created", "user_id", "created_at"),)
    id = pk(); user_id = user_fk()
    role = Column(String, default="user")    # user|assistant|tool
    content = Column(Text, default="")
    tool_name = Column(String, nullable=True)


class Integration(Base, TimestampMixin):
    __tablename__ = "integrations"
    # One row per provider per user.
    __table_args__ = (
        Index("ix_integrations_user_provider", "user_id", "provider", unique=True),
    )
    id = pk(); user_id = user_fk()
    provider = Column(String, nullable=False)  # calendar|email|github|drive|reminders|music
    status = Column(String, default="disconnected")
    scopes = Column(String, default="")
    account_label = Column(String, default="")
    last_sync_at = Column(UTCDateTime(), nullable=True)
    # Both tokens are Fernet-encrypted with a key derived from SECRET_KEY, so a
    # database dump alone does not grant access to the connected account.
    encrypted_token = Column(Text, nullable=True)
    encrypted_refresh = Column(Text, nullable=True)
    token_expires_at = Column(UTCDateTime(), nullable=True)
    # Set when a flow or a refresh fails, so the UI can say what went wrong
    # instead of showing a connection that does not work.
    last_error = Column(String, default="")

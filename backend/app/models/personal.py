from sqlalchemy import Column, String, DateTime, Text, Numeric, Boolean, Integer, Index
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_user_created", "user_id", "created_at"),)
    id = pk(); user_id = user_fk()
    text = Column(Text, nullable=False)
    category = Column(String, default="Note")   # Preference|Project|Idea|Note|Person|Fact
    source = Column(String, default="manual")   # manual|jocasta
    pinned = Column(Boolean, default=False)
    # embedding: reserved for pgvector semantic search (Milestone 2)


class Note(Base, TimestampMixin):
    __tablename__ = "notes"
    id = pk(); user_id = user_fk()
    title = Column(String, default="")
    body = Column(Text, default="")
    tags = Column(String, default="")           # comma-separated
    pinned = Column(Boolean, default=False)
    ref_type = Column(String, default="")       # course|project|topic|goal — cross-module anchor
    ref_id = Column(GUID(), nullable=True)


class FinanceEntry(Base, TimestampMixin):
    __tablename__ = "finance_entries"
    # Every finance read is "this user, this month", grouped by category.
    __table_args__ = (Index("ix_finance_user_date", "user_id", "date"),)
    id = pk(); user_id = user_fk()
    amount = Column(Numeric(12, 2), nullable=False)
    category = Column(String, default="General")
    kind = Column(String, default="expense")   # expense|income
    note = Column(String, default="")
    date = Column(UTCDateTime(), nullable=False)


class Budget(Base, TimestampMixin):
    """A monthly cap per category. Spider Sense watches these."""
    __tablename__ = "budgets"
    __table_args__ = (Index("ix_budgets_user_category", "user_id", "category", unique=True),)
    id = pk(); user_id = user_fk()
    category = Column(String, nullable=False)
    monthly_limit = Column(Numeric(12, 2), nullable=False)

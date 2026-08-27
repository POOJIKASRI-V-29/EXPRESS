from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class LearningTopic(Base, TimestampMixin):
    __tablename__ = "learning_topics"
    id = pk(); user_id = user_fk()
    name = Column(String, nullable=False)
    area = Column(String, default="DSA")   # DSA|DataScience|AI/ML|Python|Course
    state = Column(String, default="not_started")  # not_started|learning|practicing|strong|needs_revision
    progress = Column(Integer, default=0)
    course_id = Column(GUID(), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    last_reviewed_at = Column(UTCDateTime(), nullable=True)


class LearningSession(Base, TimestampMixin):
    """Logged study time. Feeds Learning, Progress and topic recency."""
    __tablename__ = "learning_sessions"
    __table_args__ = (Index("ix_sessions_user_started", "user_id", "started_at"),)
    id = pk(); user_id = user_fk()
    topic_id = Column(GUID(), ForeignKey("learning_topics.id", ondelete="CASCADE"), index=True)
    minutes = Column(Integer, default=25)
    note = Column(String, default="")
    started_at = Column(UTCDateTime(), nullable=False)


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    id = pk(); user_id = user_fk()
    name = Column(String, nullable=False)
    level = Column(Integer, default=1)
    pct = Column(Integer, default=10)


class Internship(Base, TimestampMixin):
    __tablename__ = "internships"
    id = pk(); user_id = user_fk()
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, default="Applied")  # Applied|Interviewing|In Progress|Result
    location = Column(String, default="")
    link = Column(String, default="")


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    id = pk(); user_id = user_fk()
    internship_id = Column(GUID(), ForeignKey("internships.id", ondelete="CASCADE"), index=True)
    stage = Column(String, default="applied")   # applied|oa|interview|result
    deadline = Column(UTCDateTime(), nullable=True)
    notes = Column(Text, default="")

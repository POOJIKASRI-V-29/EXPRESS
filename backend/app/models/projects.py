from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id = pk(); user_id = user_fk()
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    phase = Column(String, default="Alpha V1")
    commits = Column(Integer, default=0)
    stack = Column(String, default="")
    status = Column(String, default="Active")
    completion = Column(Integer, default=0)
    priority = Column(Integer, default=1)
    due_at = Column(UTCDateTime(), nullable=True)
    repo_url = Column(String, default="")


class ProjectPhase(Base, TimestampMixin):
    __tablename__ = "project_phases"
    id = pk()
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name = Column(String, nullable=False)
    order = Column("phase_order", Integer, default=0)
    done = Column(Boolean, default=False)


class ProjectTask(Base, TimestampMixin):
    __tablename__ = "project_tasks"
    id = pk(); user_id = user_fk()
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title = Column(String, nullable=False)
    status = Column(String, default="open")
    due_at = Column(UTCDateTime(), nullable=True)

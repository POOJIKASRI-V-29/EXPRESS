from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Date, Index
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    # Every module reads the task queue filtered by owner: by status (Tasks,
    # Home), by due window (Planner), or by the row that materialised it.
    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_due", "user_id", "due_at"),
        Index("ix_tasks_assignment", "assignment_id"),
        Index("ix_tasks_project_task", "project_task_id"),
        Index("ix_tasks_topic", "topic_id"),
        Index("ix_tasks_application", "application_id"),
    )
    id = pk(); user_id = user_fk()
    title = Column(String, nullable=False)
    category = Column(String, default="Personal")
    due_at = Column(UTCDateTime(), nullable=True)
    est_minutes = Column(Integer, default=20)
    priority = Column(String, default="med")     # low|med|high
    status = Column(String, default="open")       # open|done
    icon = Column(String, default="tasks")
    meta = Column(String, default="")
    source = Column(String, default="manual")     # manual|assignment|project|reminder|learning|career|habit
    assignment_id = Column(GUID(), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=True)
    project_task_id = Column(GUID(), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=True)
    topic_id = Column(GUID(), ForeignKey("learning_topics.id", ondelete="CASCADE"), nullable=True)
    application_id = Column(GUID(), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    postpone_count = Column(Integer, default=0)
    completed_at = Column(UTCDateTime(), nullable=True)


class Subtask(Base, TimestampMixin):
    __tablename__ = "subtasks"
    id = pk()
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title = Column(String, nullable=False)
    done = Column(Boolean, default=False)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"
    id = pk(); user_id = user_fk()
    title = Column(String, nullable=False)
    remind_at = Column(UTCDateTime(), nullable=False)
    meta = Column(String, default="")
    delivered = Column(Boolean, default=False)


class Habit(Base, TimestampMixin):
    __tablename__ = "habits"
    id = pk(); user_id = user_fk()
    title = Column(String, nullable=False)
    cadence = Column(String, default="daily")
    streak = Column(Integer, default=0)
    icon = Column(String, default="check")
    target_per_week = Column(Integer, default=7)
    archived = Column(Boolean, default=False)


class HabitLog(Base, TimestampMixin):
    """One row per day a habit was completed. Streaks are derived from these,
    never stored as the only truth."""
    __tablename__ = "habit_logs"
    # A habit may be logged at most once per day, and streaks read the whole
    # per-habit history — the unique constraint enforces the first and the
    # index serves the second.
    __table_args__ = (
        Index("ix_habit_logs_unique_day", "habit_id", "on_date", unique=True),
        Index("ix_habit_logs_user_date", "user_id", "on_date"),
    )
    id = pk(); user_id = user_fk()
    habit_id = Column(GUID(), ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    on_date = Column(Date, nullable=False, index=True)


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"
    id = pk(); user_id = user_fk()
    title = Column(String, nullable=False)
    detail = Column(Text, default="")
    horizon = Column(String, default="short")   # short|long
    category = Column(String, default="personal")
    progress = Column(Integer, default=0)       # manual floor; derived progress can exceed it
    target_date = Column(UTCDateTime(), nullable=True)
    status = Column(String, default="active")   # active|achieved|dropped


class GoalLink(Base, TimestampMixin):
    """Ties a goal to real work elsewhere in EXPRESS, so goal progress is
    derived from tasks/projects/topics instead of typed in by hand."""
    __tablename__ = "goal_links"
    # Goal progress resolves every link on each read, and a goal must not
    # accumulate duplicate links to the same row.
    __table_args__ = (
        Index("ix_goal_links_unique", "goal_id", "ref_type", "ref_id", unique=True),
    )
    id = pk(); user_id = user_fk()
    goal_id = Column(GUID(), ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    ref_type = Column(String, nullable=False)   # task|project|topic|skill|habit
    ref_id = Column(GUID(), nullable=False)

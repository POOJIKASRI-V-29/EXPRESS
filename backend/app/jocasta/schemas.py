"""Validated argument schemas for every JOCasta tool.

The planner (LLM or rules) may propose arbitrary args; these schemas are the
gate. Anything that doesn't validate is rejected before it can touch the DB.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class EmptyArgs(BaseModel):
    pass


class ScheduleArgs(BaseModel):
    """Which day's classes. Omit for today."""
    day: Optional[str] = None      # "monday" | "tomorrow" | "today"


class ProposePlanArgs(BaseModel):
    """How far ahead to plan. Capped in the executor."""
    horizon_days: int = 7


# ---- Tasks ----
class CreateTaskArgs(BaseModel):
    title: str
    category: str = "Personal"
    due_at: Optional[datetime] = None
    priority: str = "med"
    est_minutes: int = 20
    icon: str = "tasks"
    meta: str = ""


class UpdateTaskArgs(BaseModel):
    task_id: str
    title: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class TaskIdArgs(BaseModel):
    task_id: str


class RescheduleArgs(BaseModel):
    task_id: str
    due_at: datetime


class FindTaskArgs(BaseModel):
    """Lets the assistant act on a task the user named in words."""
    query: str


class CompleteByTitleArgs(BaseModel):
    query: str


class DeleteTaskArgs(BaseModel):
    """Delete a planner item the user named, or referred to as "that"."""
    query: str


class RescheduleByNameArgs(BaseModel):
    """Move a planner item the user named, without needing its id."""
    query: str
    due_at: datetime


# ---- Reminders ----
class CreateReminderArgs(BaseModel):
    title: str
    remind_at: datetime
    meta: str = ""


# ---- Memory ----
class SaveMemoryArgs(BaseModel):
    text: str
    category: str = "Note"


class SearchMemoryArgs(BaseModel):
    query: str


class MemoryIdArgs(BaseModel):
    memory_id: str


class UpdateMemoryArgs(BaseModel):
    memory_id: str
    text: Optional[str] = None
    category: Optional[str] = None
    pinned: Optional[bool] = None


# ---- Notes ----
class CreateNoteArgs(BaseModel):
    title: str = ""
    body: str
    tags: str = ""


class SearchNotesArgs(BaseModel):
    query: str


# ---- College ----
class CreateAssignmentArgs(BaseModel):
    title: str
    due_at: datetime
    course: Optional[str] = None      # matched by name/code, scoped to the user
    description: str = ""
    est_minutes: int = 60
    priority: str = "med"


class MarkAttendanceArgs(BaseModel):
    course: str
    attended: bool = True


class SetAttendanceArgs(BaseModel):
    """Correct the raw figures outright."""
    course: str
    attended_classes: int
    total_classes: int


class CreateCourseArgs(BaseModel):
    name: str
    code: str = ""
    faculty: str = ""
    credits: int = 0
    attended_classes: int = 0
    total_classes: int = 0


class UpdateCourseArgs(BaseModel):
    """Edit a course the user named. Only the fields given are changed."""
    course: str
    name: str | None = None
    code: str | None = None
    faculty: str | None = None
    room: str | None = None
    credits: int | None = None


class ScheduleClassArgs(BaseModel):
    """A recurring weekly slot for a course. Day is 0=Mon .. 6=Sun."""
    course: str
    day_of_week: int = Field(0, ge=0, le=6)
    start_time: str = "09:00"          # "HH:MM", 24h
    end_time: str = "10:30"
    room: str = ""


class RescheduleClassArgs(BaseModel):
    """Move a course's weekly slot. Fields left out keep their current value."""
    course: str
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_time: str | None = None
    end_time: str | None = None
    room: str | None = None


class CourseNameArgs(BaseModel):
    course: str


class SetDriveArgs(BaseModel):
    course: str
    url: str


class CompleteTopicArgs(BaseModel):
    """Tick a course concept the user named in words."""
    topic: str
    course: Optional[str] = None
    done: bool = True


# ---- Learning ----
class LogStudyArgs(BaseModel):
    topic: str
    minutes: int = 25
    note: str = ""


class ScheduleStudyArgs(BaseModel):
    topic: str
    due_at: datetime
    minutes: int = 45


class CreateTopicArgs(BaseModel):
    name: str
    area: str = "DSA"
    state: str = "learning"


# ---- Projects ----
class CreateProjectTaskArgs(BaseModel):
    project: str
    title: str
    due_at: Optional[datetime] = None


# ---- Personal ----
class LogHabitArgs(BaseModel):
    habit: str


class CreateHabitArgs(BaseModel):
    title: str
    cadence: str = "daily"
    target_per_week: int = 7


# ---- Finance ----
class LogExpenseArgs(BaseModel):
    amount: Decimal
    category: str = "General"
    kind: str = "expense"
    note: str = ""
    date: Optional[datetime] = None


class SetBudgetArgs(BaseModel):
    category: str
    monthly_limit: Decimal


# ---- Goals ----
class CreateGoalArgs(BaseModel):
    title: str
    detail: str = ""
    horizon: str = "short"
    category: str = "personal"
    target_date: Optional[datetime] = None


class UpdateGoalArgs(BaseModel):
    goal: str
    progress: Optional[int] = None
    status: Optional[str] = None


# ---- Spider Sense ----
class AcknowledgeSignalArgs(BaseModel):
    signal_id: str

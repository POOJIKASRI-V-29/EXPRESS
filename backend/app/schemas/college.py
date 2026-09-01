from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class SemesterOut(ORM):
    id: UUID
    label: str
    tagline: str
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]


class SemesterCreate(BaseModel):
    label: str
    tagline: str = ""
    is_active: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CourseOut(ORM):
    id: UUID
    semester_id: Optional[UUID]
    code: str
    name: str
    faculty: str
    room: str
    attendance: int
    attended_classes: int
    total_classes: int
    credits: int
    drive_url: str


class CourseCreate(BaseModel):
    name: str
    code: str = ""
    faculty: str = ""
    room: str = ""
    # Attendance is counted. Supply the real figures; leaving them at 0 means
    # "no classes held yet", which reads as "—" rather than 0%.
    attended_classes: int = 0
    total_classes: int = 0
    credits: int = 0
    drive_url: str = ""
    semester_id: Optional[UUID] = None
    # Back-compat: older clients sent a bare percentage.
    attendance: Optional[int] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    faculty: Optional[str] = None
    room: Optional[str] = None
    credits: Optional[int] = None
    drive_url: Optional[str] = None
    # Attendance is editable here too so one Edit dialog can save everything;
    # both must arrive together, and the executor still clamps attended<=held.
    attended_classes: Optional[int] = None
    total_classes: Optional[int] = None


class AttendanceCounts(BaseModel):
    """Manual correction of the raw figures."""
    attended_classes: int
    total_classes: int


class ModuleCreate(BaseModel):
    name: str
    order: Optional[int] = None


class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None


class TopicCreate(BaseModel):
    name: str
    order: Optional[int] = None


class TopicToggle(BaseModel):
    done: Optional[bool] = None      # omitted = flip


class ProposedTopic(BaseModel):
    name: str


class ProposedModule(BaseModel):
    name: str
    topics: list[str] = []


class CourseStructureIn(BaseModel):
    """Bulk module/topic creation — the shape the syllabus flow confirms."""
    modules: list[ProposedModule]
    replace: bool = False            # wipe existing modules first


class ClassOut(ORM):
    id: UUID
    course_id: Optional[UUID]
    day_of_week: int
    start_time: str
    end_time: str
    room: str


class ClassCreate(BaseModel):
    course_id: UUID
    day_of_week: int = Field(0, ge=0, le=6)     # 0 = Monday
    start_time: str = "09:00"
    end_time: str = "10:30"
    room: str = ""


class ClassUpdate(BaseModel):
    """Moving a slot. Every field optional — "move it to 10am" changes one."""
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    room: Optional[str] = None


class ExamOut(ORM):
    id: UUID
    course_id: Optional[UUID]
    title: str
    type: str
    date: datetime
    room: str


class ExamCreate(BaseModel):
    title: str
    course_id: Optional[UUID] = None
    type: str = "cat"
    date: datetime
    room: str = ""


class ExamUpdate(BaseModel):
    """Editing an exam from the planner. Every field optional — moving one only
    changes its date."""
    title: Optional[str] = None
    course_id: Optional[UUID] = None
    type: Optional[str] = None
    date: Optional[datetime] = None
    room: Optional[str] = None


class AcademicEventOut(ORM):
    id: UUID
    title: str
    type: str
    date: datetime
    end_date: Optional[datetime]


class AcademicEventCreate(BaseModel):
    title: str
    type: str = "holiday"
    date: datetime
    end_date: Optional[datetime] = None


class AcademicEventUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class AttendanceMark(BaseModel):
    attended: bool

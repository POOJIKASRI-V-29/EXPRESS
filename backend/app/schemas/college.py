from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
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


class CourseCreate(BaseModel):
    name: str
    code: str = ""
    faculty: str = ""
    room: str = ""
    attendance: int = 100
    semester_id: Optional[UUID] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    faculty: Optional[str] = None
    room: Optional[str] = None
    attendance: Optional[int] = None


class ClassOut(ORM):
    id: UUID
    course_id: Optional[UUID]
    day_of_week: int
    start_time: str
    end_time: str
    room: str


class ClassCreate(BaseModel):
    course_id: UUID
    day_of_week: int = 0
    start_time: str = "09:00"
    end_time: str = "10:30"
    room: str = ""


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


class AttendanceMark(BaseModel):
    attended: bool

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Index
from app.models.base import Base, TimestampMixin, pk, user_fk, GUID
from app.core.database import UTCDateTime


class Semester(Base, TimestampMixin):
    __tablename__ = "semesters"
    id = pk(); user_id = user_fk()
    label = Column(String, nullable=False)
    tagline = Column(String, default="")
    is_active = Column(Boolean, default=False)
    start_date = Column(UTCDateTime(), nullable=True)
    end_date = Column(UTCDateTime(), nullable=True)


class Course(Base, TimestampMixin):
    __tablename__ = "courses"
    id = pk(); user_id = user_fk()
    semester_id = Column(GUID(), ForeignKey("semesters.id", ondelete="CASCADE"), index=True)
    code = Column(String, default="")
    name = Column(String, nullable=False)
    faculty = Column(String, default="")
    room = Column(String, default="")
    attendance = Column(Integer, default=100)  # percent


class Class(Base, TimestampMixin):
    __tablename__ = "classes"
    # The planner and conflict detector both ask for "this user's slots on this weekday".
    __table_args__ = (Index("ix_classes_user_day", "user_id", "day_of_week"),)
    id = pk(); user_id = user_fk()
    course_id = Column(GUID(), ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    day_of_week = Column(Integer, default=0)   # 0=Mon
    start_time = Column(String, default="09:00")  # "HH:MM" 24h
    end_time = Column(String, default="10:30")
    room = Column(String, default="")


class AcademicEvent(Base, TimestampMixin):
    __tablename__ = "academic_events"
    __table_args__ = (Index("ix_events_user_type_date", "user_id", "type", "date"),)
    id = pk(); user_id = user_fk()
    semester_id = Column(GUID(), ForeignKey("semesters.id", ondelete="CASCADE"), nullable=True)
    title = Column(String, nullable=False)
    type = Column(String, default="holiday")   # holiday|break|exam_window|event
    date = Column(UTCDateTime(), nullable=False)
    end_date = Column(UTCDateTime(), nullable=True)


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = (Index("ix_assignments_user_status_due", "user_id", "status", "due_at"),)
    id = pk(); user_id = user_fk()
    course_id = Column(GUID(), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    due_at = Column(UTCDateTime(), nullable=False)
    est_minutes = Column(Integer, default=60)
    priority = Column(String, default="med")   # low|med|high
    status = Column(String, default="open")    # open|done


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"
    __table_args__ = (Index("ix_exams_user_date", "user_id", "date"),)
    id = pk(); user_id = user_fk()
    course_id = Column(GUID(), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    type = Column(String, default="cat")       # cat|fat|internal
    date = Column(UTCDateTime(), nullable=False)
    room = Column(String, default="")

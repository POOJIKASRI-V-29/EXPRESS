"""College: semester, courses, timetable, exams, academic calendar, attendance.

Attendance is stored as a percentage on the course and edited through explicit
marks, so the number on screen always traces back to an action the user took.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Semester, Course, Class, Exam, AcademicEvent, Assignment
from app.schemas.college import (
    SemesterOut, SemesterCreate, CourseOut, CourseCreate, CourseUpdate,
    ClassOut, ClassCreate, ExamOut, ExamCreate, AcademicEventOut, AcademicEventCreate,
    AttendanceMark,
)
from app.services import spider_sense
from app.services.timeutils import local_today, now

router = APIRouter(prefix="/college", tags=["college"])

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _own(db, model, row_id, user):
    row = db.query(model).filter(model.id == row_id, model.user_id == user.id).first()
    if not row:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


@router.get("")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Everything the College page renders, in one round trip."""
    sem = (db.query(Semester)
           .filter(Semester.user_id == user.id, Semester.is_active == True)  # noqa: E712
           .first())
    courses = db.query(Course).filter(Course.user_id == user.id).order_by(Course.code).all()
    by_id = {c.id: c for c in courses}
    classes = (db.query(Class).filter(Class.user_id == user.id)
               .order_by(Class.day_of_week, Class.start_time).all())
    assigns = (db.query(Assignment).filter(Assignment.user_id == user.id)
               .order_by(Assignment.due_at).all())
    exams = db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.date).all()
    events = (db.query(AcademicEvent).filter(AcademicEvent.user_id == user.id)
              .order_by(AcademicEvent.date).all())
    dow = local_today().weekday()

    def course_name(cid):
        c = by_id.get(cid)
        return c.name if c else ""

    return {
        "semester": None if not sem else {
            "id": str(sem.id), "label": sem.label, "tagline": sem.tagline,
            "start_date": sem.start_date.isoformat() if sem.start_date else None,
            "end_date": sem.end_date.isoformat() if sem.end_date else None,
        },
        "attendance": round(sum(c.attendance for c in courses) / len(courses)) if courses else 0,
        "attendance_floor": spider_sense.ATTENDANCE_FLOOR,
        "courses": [{"id": str(c.id), "code": c.code, "name": c.name, "faculty": c.faculty,
                     "room": c.room, "attendance": c.attendance,
                     "at_risk": (c.attendance or 0) < spider_sense.ATTENDANCE_FLOOR,
                     "assignments_open": len([a for a in assigns
                                              if a.course_id == c.id and a.status == "open"])}
                    for c in courses],
        "timetable": [{"id": str(cl.id), "day": cl.day_of_week, "day_label": DAYS[cl.day_of_week % 7],
                       "start": cl.start_time, "end": cl.end_time,
                       "room": cl.room or course_name(cl.course_id),
                       "course_id": str(cl.course_id) if cl.course_id else None,
                       "course": course_name(cl.course_id),
                       "today": cl.day_of_week == dow}
                      for cl in classes],
        "today": [{"id": str(cl.id), "start": cl.start_time, "end": cl.end_time,
                   "name": course_name(cl.course_id), "room": cl.room,
                   "course_id": str(cl.course_id) if cl.course_id else None}
                  for cl in classes if cl.day_of_week == dow],
        "assignments": [{"id": str(a.id), "title": a.title, "desc": a.description,
                         "due_at": a.due_at.isoformat(), "status": a.status,
                         "priority": a.priority, "est_minutes": a.est_minutes,
                         "course_id": str(a.course_id) if a.course_id else None,
                         "course": course_name(a.course_id)} for a in assigns],
        "exams": [{"id": str(e.id), "title": e.title, "type": e.type,
                   "date": e.date.isoformat(), "room": e.room,
                   "course": course_name(e.course_id)} for e in exams],
        "events": [{"id": str(ev.id), "title": ev.title, "type": ev.type,
                    "date": ev.date.isoformat(),
                    "end_date": ev.end_date.isoformat() if ev.end_date else None}
                   for ev in events],
    }


# ---- Semester ----
@router.get("/semesters", response_model=list[SemesterOut])
def list_semesters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Semester).filter(Semester.user_id == user.id).order_by(Semester.created_at).all()


@router.post("/semesters", response_model=SemesterOut, status_code=201)
def create_semester(body: SemesterCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if body.is_active:
        for s in db.query(Semester).filter(Semester.user_id == user.id).all():
            s.is_active = False
    s = Semester(user_id=user.id, **body.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return s


# ---- Courses ----
@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Course).filter(Course.user_id == user.id).order_by(Course.code).all()


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = body.model_dump()
    if not data.get("semester_id"):
        sem = (db.query(Semester)
               .filter(Semester.user_id == user.id, Semester.is_active == True)  # noqa: E712
               .first())
        data["semester_id"] = sem.id if sem else None
    c = Course(user_id=user.id, **data)
    db.add(c); db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.patch("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: str, body: CourseUpdate, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    c = _own(db, Course, course_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)   # attendance edits can raise/clear a signal
    return c


@router.post("/courses/{course_id}/attendance", response_model=CourseOut)
def mark_attendance(course_id: str, body: AttendanceMark, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    """Record one class as attended or missed.

    Held classes are inferred from the timetable rather than a counter: each
    weekly slot is one class, so a single mark moves the percentage by a
    proportional, explainable amount instead of a magic number.
    """
    c = _own(db, Course, course_id, user)
    slots = db.query(Class).filter(Class.user_id == user.id, Class.course_id == c.id).count() or 1
    step = max(1, round(100 / (slots * 15)))   # ~15 teaching weeks per semester
    c.attendance = max(0, min(100, (c.attendance or 0) + (step if body.attended else -step)))
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = _own(db, Course, course_id, user)
    db.delete(c); db.commit()
    return


# ---- Timetable ----
@router.post("/classes", response_model=ClassOut, status_code=201)
def create_class(body: ClassCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    course = _own(db, Course, body.course_id, user)
    data = body.model_dump()
    data["room"] = data.get("room") or course.room
    cl = Class(user_id=user.id, **data)
    db.add(cl); db.commit(); db.refresh(cl)
    spider_sense.scan(db, user)   # a new slot can create a conflict
    return cl


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    cl = _own(db, Class, class_id, user)
    db.delete(cl); db.commit()
    return


# ---- Exams ----
@router.post("/exams", response_model=ExamOut, status_code=201)
def create_exam(body: ExamCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = Exam(user_id=user.id, **body.model_dump())
    db.add(e); db.commit(); db.refresh(e)
    spider_sense.scan(db, user)
    return e


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = _own(db, Exam, exam_id, user)
    db.delete(e); db.commit()
    return


# ---- Academic calendar ----
@router.post("/events", response_model=AcademicEventOut, status_code=201)
def create_event(body: AcademicEventCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ev = AcademicEvent(user_id=user.id, **body.model_dump())
    db.add(ev); db.commit(); db.refresh(ev)
    spider_sense.scan(db, user)
    return ev


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ev = _own(db, AcademicEvent, event_id, user)
    db.delete(ev); db.commit()
    return

"""College: semester, courses, timetable, exams, academic calendar, attendance.

Attendance is stored as a percentage on the course and edited through explicit
marks, so the number on screen always traces back to an action the user took.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import (Semester, Course, Class, Exam, AcademicEvent, Assignment,
                        CourseModule, CourseTopic)
from app.schemas.college import (
    SemesterOut, SemesterCreate, CourseOut, CourseCreate, CourseUpdate,
    ClassOut, ClassCreate, ClassUpdate, ExamOut, ExamCreate, ExamUpdate,
    AcademicEventOut, AcademicEventCreate, AcademicEventUpdate,
    AttendanceMark, AttendanceCounts, ModuleCreate, ModuleUpdate, TopicCreate,
    TopicToggle, CourseStructureIn,
)
from app.services import spider_sense
from app.services import courses as course_svc
from app.services.timeutils import local_today, now

router = APIRouter(prefix="/college", tags=["college"])


def _overall_attendance(courses) -> int:
    """Mean attendance across courses that have held at least one class."""
    counted = [c for c in courses if (c.total_classes or 0) > 0]
    if not counted:
        return 0
    return round(sum(course_svc.pct(c.attended_classes, c.total_classes)
                     for c in counted) / len(counted))

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
        # Averaged over courses that have actually held classes. A course with
        # nothing held has no attendance to average — counting it as 0% drags
        # the figure down and reads as a failing record rather than no record.
        "attendance": _overall_attendance(courses),
        "attendance_floor": spider_sense.ATTENDANCE_FLOOR,
        "courses": [{**course_svc.summarize(db, user, c),
                     # Only "at risk" once classes have actually been held —
                     # a brand-new course has no attendance to be bad.
                     "at_risk": (c.total_classes or 0) > 0
                                and course_svc.pct(c.attended_classes, c.total_classes)
                                    < spider_sense.ATTENDANCE_FLOOR,
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
    legacy_pct = data.pop("attendance", None)
    if not data.get("semester_id"):
        sem = (db.query(Semester)
               .filter(Semester.user_id == user.id, Semester.is_active == True)  # noqa: E712
               .first())
        data["semester_id"] = sem.id if sem else None
    c = Course(user_id=user.id, **data)
    # A client that still sends a bare percentage gets it expressed as counts,
    # which preserves the number exactly and gives the counters a real basis.
    if legacy_pct is not None and not data.get("total_classes"):
        course_svc.set_counts(c, int(legacy_pct), 100)
    else:
        course_svc.recompute(c)
    db.add(c); db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.patch("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: str, body: CourseUpdate, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    c = _own(db, Course, course_id, user)
    fields = body.model_dump(exclude_none=True)
    # Attendance goes through the service, never straight onto the column: it
    # clamps attended to held and recomputes the cached percent. Setting the
    # raw attributes here would let one edit dialog produce 60/50 = 120%.
    attended = fields.pop("attended_classes", None)
    total = fields.pop("total_classes", None)
    for k, v in fields.items():
        setattr(c, k, v)
    if attended is not None or total is not None:
        course_svc.set_counts(c,
                              c.attended_classes if attended is None else attended,
                              c.total_classes if total is None else total)
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.post("/courses/{course_id}/attendance", response_model=CourseOut)
def mark_attendance(course_id: str, body: AttendanceMark, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    """Record one held class as attended or missed.

    Both outcomes increment the classes-held count — that is why missing one
    lowers the percentage. The figure is always attended/held, so it can be
    explained rather than asserted.
    """
    c = _own(db, Course, course_id, user)
    course_svc.mark(c, body.attended)
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.post("/courses/{course_id}/attendance/undo", response_model=CourseOut)
def undo_attendance(course_id: str, body: AttendanceMark, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    """Undo one recorded class — for a mis-tap."""
    c = _own(db, Course, course_id, user)
    course_svc.unmark(c, body.attended)
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


@router.patch("/courses/{course_id}/attendance", response_model=CourseOut)
def set_attendance(course_id: str, body: AttendanceCounts, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    """Set the raw figures directly. Attended is clamped to at most held."""
    c = _own(db, Course, course_id, user)
    course_svc.set_counts(c, body.attended_classes, body.total_classes)
    db.commit(); db.refresh(c)
    spider_sense.scan(db, user)
    return c


# ---- Course workspace: modules and topics ----
@router.get("/courses/{course_id}")
def course_workspace(course_id: str, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    """Everything the course page renders."""
    return course_svc.workspace(db, user, _own(db, Course, course_id, user))


@router.post("/courses/{course_id}/modules", status_code=201)
def add_module(course_id: str, body: ModuleCreate, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    c = _own(db, Course, course_id, user)
    count = (db.query(CourseModule)
             .filter(CourseModule.course_id == c.id, CourseModule.user_id == user.id).count())
    db.add(CourseModule(user_id=user.id, course_id=c.id, name=body.name,
                        order=body.order if body.order is not None else count))
    db.commit()
    return course_svc.workspace(db, user, c)


@router.patch("/modules/{module_id}")
def update_module(module_id: str, body: ModuleUpdate, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    m = _own(db, CourseModule, module_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    return course_svc.workspace(db, user, _own(db, Course, m.course_id, user))


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(module_id: str, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    m = _own(db, CourseModule, module_id, user)
    db.delete(m); db.commit()
    return


@router.post("/modules/{module_id}/topics", status_code=201)
def add_topic(module_id: str, body: TopicCreate, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    m = _own(db, CourseModule, module_id, user)
    count = (db.query(CourseTopic)
             .filter(CourseTopic.module_id == m.id, CourseTopic.user_id == user.id).count())
    db.add(CourseTopic(user_id=user.id, module_id=m.id, name=body.name,
                       order=body.order if body.order is not None else count))
    db.commit()
    return course_svc.workspace(db, user, _own(db, Course, m.course_id, user))


@router.post("/topics/{topic_id}/toggle")
def toggle_topic(topic_id: str, body: TopicToggle | None = None,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Tick or untick a concept. This is the only thing that moves course
    progress, which is counted from these rows."""
    t = _own(db, CourseTopic, topic_id, user)
    want = (body.done if body and body.done is not None else not t.done)
    course_svc.set_topic_done(db, t, want)
    db.commit()
    m = _own(db, CourseModule, t.module_id, user)
    return course_svc.workspace(db, user, _own(db, Course, m.course_id, user))


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    t = _own(db, CourseTopic, topic_id, user)
    db.delete(t); db.commit()
    return


@router.post("/courses/{course_id}/structure", status_code=201)
def create_structure(course_id: str, body: CourseStructureIn, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    """Create modules and their topics in bulk.

    This is what a confirmed syllabus proposal lands on. It is deliberately a
    separate, explicit endpoint rather than something the extraction step can
    trigger on its own.
    """
    c = _own(db, Course, course_id, user)
    if body.replace:
        for m in (db.query(CourseModule)
                  .filter(CourseModule.course_id == c.id,
                          CourseModule.user_id == user.id).all()):
            db.delete(m)
        db.flush()
    base = (db.query(CourseModule)
            .filter(CourseModule.course_id == c.id, CourseModule.user_id == user.id).count())
    for i, mod in enumerate(body.modules):
        m = CourseModule(user_id=user.id, course_id=c.id, name=mod.name, order=base + i)
        db.add(m); db.flush()
        for j, topic in enumerate(mod.topics):
            db.add(CourseTopic(user_id=user.id, module_id=m.id, name=topic, order=j))
    db.commit()
    return course_svc.workspace(db, user, c)


@router.get("/courses/{course_id}/impact")
def course_delete_impact(course_id: str, db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    """What deleting this course would remove.

    The UI shows these counts before asking. Deleting a course is the one
    action here that reaches several tables at once, and a confirmation that
    can't say what it will destroy isn't really a confirmation.
    """
    c = _own(db, Course, course_id, user)
    modules = db.query(CourseModule).filter(CourseModule.course_id == c.id).all()
    module_ids = [m.id for m in modules]
    topics = (db.query(CourseTopic).filter(CourseTopic.module_id.in_(module_ids)).count()
              if module_ids else 0)
    return {
        "course": c.name,
        "modules": len(modules),
        "concepts": topics,
        "classes": db.query(Class).filter(Class.course_id == c.id).count(),
        # Assignments and their planner items survive: the FK is SET NULL, so
        # coursework you still owe is kept and simply stops naming the course.
        "assignments_kept": db.query(Assignment).filter(
            Assignment.course_id == c.id).count(),
        "exams": db.query(Exam).filter(Exam.course_id == c.id).count(),
    }


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Delete a course and the academic structure that only exists inside it.

    Modules, concepts, timetable slots and exams belong to the course and go
    with it. Assignments do not: they are detached, so coursework the user still
    owes survives and simply stops naming the course — and the planner items
    derived from those assignments survive with them.

    The children are removed explicitly rather than left to `ondelete`. The FK
    cascades only fire where the database enforces them, which Postgres does and
    SQLite (the test database) does not — relying on them would mean the tested
    behaviour and the shipped behaviour were different things.
    """
    c = _own(db, Course, course_id, user)

    module_ids = [m.id for m in
                  db.query(CourseModule).filter(CourseModule.course_id == c.id).all()]
    if module_ids:
        (db.query(CourseTopic).filter(CourseTopic.module_id.in_(module_ids))
           .delete(synchronize_session=False))
        (db.query(CourseModule).filter(CourseModule.course_id == c.id)
           .delete(synchronize_session=False))
    db.query(Class).filter(Class.course_id == c.id).delete(synchronize_session=False)
    db.query(Exam).filter(Exam.course_id == c.id).delete(synchronize_session=False)
    # Kept, not deleted — see the docstring.
    (db.query(Assignment).filter(Assignment.course_id == c.id)
       .update({Assignment.course_id: None}, synchronize_session=False))

    db.delete(c); db.commit()
    spider_sense.scan(db, user)
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


@router.patch("/classes/{class_id}", response_model=ClassOut)
def update_class(class_id: str, body: ClassUpdate, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    """Move a timetable slot — a different day, a different hour, a new room."""
    cl = _own(db, Class, class_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cl, k, v)
    db.commit(); db.refresh(cl)
    spider_sense.scan(db, user)   # a moved slot can create or clear a conflict
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


@router.patch("/exams/{exam_id}", response_model=ExamOut)
def update_exam(exam_id: str, body: ExamUpdate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    """Correct an exam from the planner — a wrong date, a room, a typo."""
    ex = _own(db, Exam, exam_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ex, k, v)
    db.commit(); db.refresh(ex)
    spider_sense.scan(db, user)   # a moved exam changes what is urgent
    return ex


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


@router.patch("/events/{event_id}", response_model=AcademicEventOut)
def update_event(event_id: str, body: AcademicEventUpdate, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    """Correct an academic calendar entry from the planner."""
    ev = _own(db, AcademicEvent, event_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ev, k, v)
    db.commit(); db.refresh(ev)
    spider_sense.scan(db, user)
    return ev


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ev = _own(db, AcademicEvent, event_id, user)
    db.delete(ev); db.commit()
    return

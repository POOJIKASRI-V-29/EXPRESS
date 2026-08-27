"""Planner: one timeline over everything with a time on it.

Classes come from the timetable, everything else arrives as a Task — because
assignments, project work, study blocks and career deadlines all materialise
into Tasks, the Planner needs no per-module special cases. Conflicts are the
same ones Spider Sense reports, read from the same detector.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Task, Class, Course, Exam, AcademicEvent, Reminder
from app.services import spider_sense
from app.services.timeutils import local_hhmm, local_now, local_today, start_of_local_day, now

router = APIRouter(prefix="/planner", tags=["planner"])

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CATEGORY_ICON = {"College": "college", "Learning": "learning", "Project": "projects",
                 "Career": "career", "Routine": "check", "Personal": "tasks"}


class MoveIn(BaseModel):
    due_at: str


def _hhmm(dt) -> str:
    """Render a stored UTC instant on the user's clock, not the server's."""
    return local_hhmm(dt)


def _day_payload(db, user, offset: int) -> dict:
    """Everything scheduled for the local day `offset` days from today."""
    start = start_of_local_day(offset)
    end = start + timedelta(days=1)
    the_date = local_today() + timedelta(days=offset)
    dow = the_date.weekday()

    items = []

    rows = (db.query(Class, Course).join(Course, Class.course_id == Course.id)
            .filter(Class.user_id == user.id, Class.day_of_week == dow).all())
    for cl, c in rows:
        items.append({"id": str(cl.id), "kind": "class", "time": cl.start_time,
                      "end": cl.end_time, "title": c.name, "meta": cl.room or c.room,
                      "icon": "college", "status": "fixed", "movable": False})

    tasks = (db.query(Task)
             .filter(Task.user_id == user.id, Task.due_at >= start, Task.due_at < end)
             .order_by(Task.due_at).all())
    for t in tasks:
        items.append({"id": str(t.id), "kind": "task", "time": _hhmm(t.due_at),
                      "end": None, "title": t.title,
                      "meta": t.meta or t.category, "icon": t.icon or CATEGORY_ICON.get(t.category, "tasks"),
                      "status": t.status, "priority": t.priority, "category": t.category,
                      "source": t.source, "est_minutes": t.est_minutes, "movable": True})

    for ex in (db.query(Exam)
               .filter(Exam.user_id == user.id, Exam.date >= start, Exam.date < end).all()):
        items.append({"id": str(ex.id), "kind": "exam", "time": _hhmm(ex.date), "end": None,
                      "title": ex.title, "meta": ex.room or ex.type.upper(),
                      "icon": "college", "status": "fixed", "movable": False})

    for ev in (db.query(AcademicEvent)
               .filter(AcademicEvent.user_id == user.id,
                       AcademicEvent.date >= start, AcademicEvent.date < end).all()):
        items.append({"id": str(ev.id), "kind": "event", "time": _hhmm(ev.date),
                      "end": _hhmm(ev.end_date) if ev.end_date else None,
                      "title": ev.title, "meta": ev.type.replace("_", " "),
                      "icon": "cal", "status": "fixed", "movable": False})

    for r in (db.query(Reminder)
              .filter(Reminder.user_id == user.id,
                      Reminder.remind_at >= start, Reminder.remind_at < end).all()):
        items.append({"id": str(r.id), "kind": "reminder", "time": _hhmm(r.remind_at), "end": None,
                      "title": r.title, "meta": r.meta or "Reminder", "icon": "bell",
                      "status": "delivered" if r.delivered else "pending", "movable": False})

    items.sort(key=lambda x: x["time"])
    booked = sum(i.get("est_minutes") or 0 for i in items if i["kind"] == "task" and i["status"] == "open")
    return {
        "offset": offset,
        "date": the_date.isoformat(),
        "day_label": DAYS[dow],
        "is_today": offset == 0,
        "items": items,
        "open_count": len([i for i in items if i.get("status") == "open"]),
        "booked_minutes": booked,
    }


@router.get("")
def get_planner(days: int = 7, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Today plus the next `days-1` days, and today's conflicts."""
    days = max(1, min(days, 14))
    spider_sense.scan(db, user)
    conflicts = [{"key": k, "title": t} for k, t in spider_sense._detect_conflicts(db, user.id)]
    unscheduled = (db.query(Task)
                   .filter(Task.user_id == user.id, Task.status == "open", Task.due_at.is_(None))
                   .order_by(Task.created_at.desc()).all())
    return {
        "now": local_now().strftime("%H:%M"),
        "today": _day_payload(db, user, 0),
        "days": [_day_payload(db, user, i) for i in range(days)],
        "conflicts": conflicts,
        "unscheduled": [{"id": str(t.id), "title": t.title, "meta": t.meta or t.category,
                         "icon": t.icon, "priority": t.priority, "est_minutes": t.est_minutes}
                        for t in unscheduled],
    }


@router.get("/day/{offset}")
def get_day(offset: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _day_payload(db, user, offset)


@router.post("/schedule/{task_id}")
def schedule_task(task_id: str, body: MoveIn, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    """Give an undated task a slot, or move a dated one. Uses the same
    postpone accounting as /tasks/{id}/reschedule so Spider Sense still notices
    a task being pushed repeatedly."""
    from datetime import datetime
    t = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    had_date = t.due_at is not None
    t.due_at = datetime.fromisoformat(body.due_at.replace("Z", "+00:00"))
    if had_date:
        t.postpone_count = (t.postpone_count or 0) + 1
    db.commit()
    spider_sense.scan(db, user)
    db.refresh(t)
    return {"id": str(t.id), "due_at": t.due_at.isoformat(), "postpone_count": t.postpone_count}

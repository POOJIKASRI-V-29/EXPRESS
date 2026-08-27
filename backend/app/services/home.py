"""Dynamic Home: server decides the time context and what to surface."""
from datetime import timedelta
from app.models import Task, Assignment, Course, Class, Semester
from app.services.timeutils import now, local_now
from app.services import spider_sense


def time_context(dt=None) -> str:
    dt = dt or local_now()
    h = dt.hour
    if 5 <= h < 9:
        return "morning"
    if 9 <= h < 15:
        return "college"
    if 15 <= h < 21:
        return "evening"
    return "night"


def build_home(db, user) -> dict:
    uid = user.id
    ctx = time_context()
    open_assigns = (
        db.query(Assignment)
        .filter(Assignment.user_id == uid, Assignment.status == "open")
        .order_by(Assignment.due_at.asc())
        .all()
    )
    focus = open_assigns[0] if open_assigns else None
    up_next = (
        db.query(Task)
        .filter(Task.user_id == uid, Task.status == "open", Task.source == "manual")
        .order_by(Task.due_at.asc())
        .limit(2)
        .all()
    )
    courses = db.query(Course).filter(Course.user_id == uid).all()
    attendance = round(sum(c.attendance for c in courses) / len(courses)) if courses else 0
    sem = db.query(Semester).filter(Semester.user_id == uid, Semester.is_active == True).first()  # noqa: E712

    signals = spider_sense.active(db, user)
    banner = next((s for s in signals if s.level in ("action", "critical")), None)

    return {
        "time_context": ctx,
        "greeting": {"morning": "Good morning", "college": "In session",
                     "evening": "Good evening", "night": "Winding down"}[ctx],
        "user_name": user.name,
        "semester": sem.label if sem else "",
        "focus": None if not focus else {
            "id": str(focus.id), "title": focus.title, "est_minutes": focus.est_minutes,
            "course": next((c.name for c in courses if c.id == focus.course_id), "Personal"),
        },
        "up_next": [
            {"id": str(t.id), "title": t.title, "meta": t.meta, "due_at": t.due_at.isoformat() if t.due_at else None,
             "icon": t.icon}
            for t in up_next
        ],
        "attendance": attendance,
        # Distinguishes "0% attendance" from "no courses to have attendance in" —
        # without it a brand-new account is shown a red 0% risk it cannot act on.
        "course_count": len(courses),
        "banner": None if not banner else {"level": banner.level, "title": banner.title, "id": str(banner.id)},
    }

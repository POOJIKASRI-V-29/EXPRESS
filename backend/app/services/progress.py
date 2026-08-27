"""Progress: one honest rollup across every module.

Every number here is counted from real rows. Where a module has no data yet the
count is zero and the UI is told the section is empty — nothing is estimated.
"""
from datetime import timedelta
from app.models import (Task, Assignment, Memory, Course, Note, Project, LearningTopic,
                        LearningSession, Skill, Internship, Application, Goal, Habit, Notification)
from app.services.timeutils import now, local_today, start_of_local_day
from app.services import goals as goals_svc, habits as habits_svc, finance as finance_svc


def snapshot(db, user) -> dict:
    """Compact rollup — the shape JOCasta and Home read."""
    uid = user.id
    tasks = db.query(Task).filter(Task.user_id == uid).all()
    done = len([t for t in tasks if t.status == "done"])
    courses = db.query(Course).filter(Course.user_id == uid).all()
    attendance = round(sum(c.attendance for c in courses) / len(courses)) if courses else 0
    return {
        "tasks_total": len(tasks),
        "tasks_done": done,
        "attendance": attendance,
        "memories": db.query(Memory).filter(Memory.user_id == uid).count(),
    }


def _completion_series(db, uid, days: int = 14) -> list[dict]:
    """Tasks completed per local day for the last `days` days."""
    start = start_of_local_day(-(days - 1))
    rows = (db.query(Task)
            .filter(Task.user_id == uid, Task.status == "done",
                    Task.completed_at.isnot(None), Task.completed_at >= start).all())
    buckets: dict[str, int] = {}
    for t in rows:
        key = t.completed_at.date().isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    today = local_today()
    return [{"date": (today - timedelta(days=i)).isoformat(),
             "count": buckets.get((today - timedelta(days=i)).isoformat(), 0)}
            for i in range(days - 1, -1, -1)]


def _study_minutes(db, uid, days: int = 14) -> dict:
    start = start_of_local_day(-(days - 1))
    rows = (db.query(LearningSession)
            .filter(LearningSession.user_id == uid, LearningSession.started_at >= start).all())
    total = sum(r.minutes or 0 for r in rows)
    by_day: dict[str, int] = {}
    for r in rows:
        key = r.started_at.date().isoformat()
        by_day[key] = by_day.get(key, 0) + (r.minutes or 0)
    today = local_today()
    return {
        "total_minutes": total,
        "session_count": len(rows),
        "series": [{"date": (today - timedelta(days=i)).isoformat(),
                    "minutes": by_day.get((today - timedelta(days=i)).isoformat(), 0)}
                   for i in range(days - 1, -1, -1)],
    }


def report(db, user) -> dict:
    """Full Progress page payload — every module reporting its own real state."""
    uid = user.id
    tasks = db.query(Task).filter(Task.user_id == uid).all()
    done = [t for t in tasks if t.status == "done"]
    open_tasks = [t for t in tasks if t.status == "open"]
    overdue = [t for t in open_tasks if t.due_at and t.due_at < now()]

    courses = db.query(Course).filter(Course.user_id == uid).all()
    assigns = db.query(Assignment).filter(Assignment.user_id == uid).all()
    topics = db.query(LearningTopic).filter(LearningTopic.user_id == uid).all()
    skills = db.query(Skill).filter(Skill.user_id == uid).all()
    projects = db.query(Project).filter(Project.user_id == uid).all()
    apps = db.query(Application).filter(Application.user_id == uid).all()
    goal_rows = goals_svc.listing(db, user)
    habit_rows = habits_svc.summary(db, user)

    attendance = round(sum(c.attendance for c in courses) / len(courses)) if courses else 0
    study = _study_minutes(db, uid)

    return {
        "generated_at": now().isoformat(),
        "tasks": {
            "total": len(tasks), "done": len(done), "open": len(open_tasks),
            "overdue": len(overdue),
            "completion_pct": round(len(done) / len(tasks) * 100) if tasks else 0,
            "series": _completion_series(db, uid),
        },
        "college": {
            "courses": len(courses), "attendance": attendance,
            "at_risk": [{"name": c.name, "attendance": c.attendance}
                        for c in courses if (c.attendance or 0) < 75],
            "assignments_total": len(assigns),
            "assignments_done": len([a for a in assigns if a.status == "done"]),
        },
        "learning": {
            "topics": len(topics),
            "strong": len([t for t in topics if t.state == "strong"]),
            "needs_revision": len([t for t in topics if t.state == "needs_revision"]),
            "avg_progress": round(sum(t.progress or 0 for t in topics) / len(topics)) if topics else 0,
            "skills": len(skills),
            "avg_skill": round(sum(s.pct or 0 for s in skills) / len(skills)) if skills else 0,
            **study,
        },
        "projects": {
            "total": len(projects),
            "active": len([p for p in projects if p.status == "Active"]),
            "avg_completion": round(sum(p.completion or 0 for p in projects) / len(projects)) if projects else 0,
        },
        "career": {
            "applications": len(apps),
            "interviewing": len([a for a in apps if a.stage == "interview"]),
            "by_stage": {s: len([a for a in apps if a.stage == s])
                         for s in ("applied", "oa", "interview", "result")},
        },
        "goals": {
            "total": len(goal_rows),
            "active": len([g for g in goal_rows if g["status"] == "active"]),
            "achieved": len([g for g in goal_rows if g["status"] == "achieved"]),
            "avg_progress": round(sum(g["progress"] for g in goal_rows) / len(goal_rows)) if goal_rows else 0,
        },
        "habits": {
            "total": len(habit_rows),
            "done_today": len([h for h in habit_rows if h["done_today"]]),
            "best_streak": max([h["streak"] for h in habit_rows], default=0),
        },
        "personal": {
            "notes": db.query(Note).filter(Note.user_id == uid).count(),
            "memories": db.query(Memory).filter(Memory.user_id == uid).count(),
        },
        "finance": finance_svc.summary(db, user),
        "signals": {
            "active": db.query(Notification).filter(
                Notification.user_id == uid,
                Notification.acknowledged == False,  # noqa: E712
                Notification.resolved == False).count(),  # noqa: E712
        },
    }

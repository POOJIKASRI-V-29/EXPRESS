"""Habit streaks are derived from HabitLog rows, never trusted from a counter.

`Habit.streak` is kept as a cached mirror so list endpoints stay cheap, but it
is always recomputed from the logs whenever a habit is toggled.
"""
from datetime import timedelta
from app.models import Habit, HabitLog
from app.services.timeutils import local_today


def logged_dates(db, user, habit_id) -> set:
    rows = (db.query(HabitLog)
            .filter(HabitLog.user_id == user.id, HabitLog.habit_id == habit_id).all())
    return {r.on_date for r in rows}


def current_streak(dates: set, today=None) -> int:
    """Consecutive days ending today (or yesterday, if today isn't logged yet —
    a habit shouldn't look broken at 9am)."""
    if not dates:
        return 0
    today = today or local_today()
    anchor = today if today in dates else today - timedelta(days=1)
    if anchor not in dates:
        return 0
    streak, cur = 0, anchor
    while cur in dates:
        streak += 1
        cur -= timedelta(days=1)
    return streak


def recompute(db, user, habit: Habit) -> Habit:
    dates = logged_dates(db, user, habit.id)
    habit.streak = current_streak(dates)
    return habit


def week_matrix(dates: set, today=None) -> list[bool]:
    """Last 7 days, oldest first — drives the little dot row in the UI."""
    today = today or local_today()
    return [(today - timedelta(days=i)) in dates for i in range(6, -1, -1)]


def summary(db, user) -> list[dict]:
    """All habits with derived streaks.

    Logs for every habit are fetched in one query and grouped in memory rather
    than one query per habit — this runs on the Personal page, in JOCasta's
    context, and inside a Spider Sense detector.
    """
    habits = (db.query(Habit)
              .filter(Habit.user_id == user.id, Habit.archived == False)  # noqa: E712
              .order_by(Habit.created_at.asc()).all())
    if not habits:
        return []

    by_habit: dict = {}
    for row in db.query(HabitLog).filter(HabitLog.user_id == user.id).all():
        by_habit.setdefault(row.habit_id, set()).add(row.on_date)

    today = local_today()
    out = []
    for h in habits:
        dates = by_habit.get(h.id, set())
        h.streak = current_streak(dates, today)
        out.append({
            "id": str(h.id), "title": h.title, "cadence": h.cadence, "icon": h.icon,
            "streak": h.streak, "target_per_week": h.target_per_week,
            "done_today": today in dates,
            "week": week_matrix(dates, today),
            "done_this_week": sum(1 for i in range(7) if (today - timedelta(days=i)) in dates),
        })
    db.commit()
    return out

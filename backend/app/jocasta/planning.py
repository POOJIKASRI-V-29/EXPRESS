"""Deterministic day/week planning.

This is the reasoning behind "help me plan" — and it deliberately does NOT
depend on the LLM. A student without an API key still gets a real plan, and a
student with one gets the same allocator backing up the model's suggestions.

The allocator is intentionally simple and explainable:

  1. Collect work that needs time: overdue tasks, tasks due inside the horizon,
     and topics flagged for revision ahead of an exam.
  2. Collect real capacity per day from `context.capacity` — waking hours minus
     class time minus what is already committed.
  3. Place the most urgent work first, into the latest day that still precedes
     its deadline and has room. Latest-fit rather than earliest-fit keeps the
     near days free for whatever arrives tomorrow.
  4. Emit tool intents. Nothing is written here — the caller gates them through
     `safety`, so the user sees the plan before it happens.

Every proposal carries the reason it was made, so the plan can be explained
rather than merely obeyed.
"""
from datetime import datetime, timedelta

from app.models import Task, Exam, LearningTopic, Course
from app.jocasta import context as ctx_mod
from app.services.timeutils import now, local_today, start_of_local_day, hours_until

# Don't fill a day to the brim; leave room for life.
USABLE_FRACTION = 0.6
MIN_BLOCK_MINUTES = 20
DEFAULT_REVISION_MINUTES = 60


def _slot_datetime(day_offset: int, hour: int = 19, minute: int = 0) -> datetime:
    """A working slot on the given day, as a UTC instant.

    Today is special: if the default evening hour has already gone by, the slot
    becomes "shortly from now" instead. Without this, asking for a plan at 9pm
    would find today unusable and push everything to tomorrow.
    """
    base = start_of_local_day(day_offset) + timedelta(hours=hour, minutes=minute)
    if day_offset == 0:
        soon = now() + timedelta(minutes=30)
        if base < soon:
            return soon
    return base


def _work_items(db, user, horizon_days: int) -> list[dict]:
    """Everything competing for time, most urgent first."""
    horizon = now() + timedelta(days=horizon_days)
    items = []

    tasks = (db.query(Task)
             .filter(Task.user_id == user.id, Task.status == "open")
             .order_by(Task.due_at.is_(None), Task.due_at).all())
    for t in tasks:
        overdue = t.due_at is not None and t.due_at < now()
        in_range = t.due_at is not None and t.due_at <= horizon
        if not (overdue or in_range):
            continue
        # A task materialised from an assignment carries a real external
        # deadline. Moving it would move the coursework due date itself, so
        # such work gets a preparation block placed *before* the deadline
        # instead — the deadline is never touched by planning.
        external = t.assignment_id is not None or t.application_id is not None
        items.append({
            "kind": "task", "id": str(t.id), "title": t.title,
            "minutes": max(MIN_BLOCK_MINUTES, t.est_minutes or 30),
            "due_at": t.due_at, "overdue": overdue, "external_deadline": external,
            "category": t.category, "priority": {"high": 0, "med": 1, "low": 2}.get(t.priority, 1),
            "moved": t.postpone_count or 0,
        })

    # Revision ahead of an exam: the topic is flagged, the exam is close, and
    # nothing is scheduled for it yet.
    exams = (db.query(Exam)
             .filter(Exam.user_id == user.id, Exam.date >= now(), Exam.date <= horizon)
             .order_by(Exam.date).all())
    if exams:
        courses = {c.id: c.name for c in db.query(Course).filter(Course.user_id == user.id).all()}
        already = {t.topic_id for t in db.query(Task).filter(
            Task.user_id == user.id, Task.status == "open", Task.topic_id.isnot(None)).all()}
        topics = (db.query(LearningTopic)
                  .filter(LearningTopic.user_id == user.id,
                          LearningTopic.state.in_(("needs_revision", "learning")))
                  .all())
        for ex in exams:
            course_name = courses.get(ex.course_id, "")
            for tp in topics:
                if tp.id in already:
                    continue
                relevant = (tp.course_id == ex.course_id) or (
                    course_name and course_name.lower().split()[0] in (tp.name or "").lower())
                if not relevant:
                    continue
                items.append({
                    "kind": "revision", "id": str(tp.id), "title": tp.name,
                    "minutes": DEFAULT_REVISION_MINUTES,
                    # revision must land before the exam, not on the day of it
                    "due_at": ex.date - timedelta(hours=12),
                    "overdue": False, "priority": 0, "moved": 0,
                    "external_deadline": True, "category": "Learning",
                    "because": f"{ex.title} on {ex.date.date().isoformat()}",
                })

    items.sort(key=lambda x: (not x["overdue"], x["due_at"] or now() + timedelta(days=999),
                              x["priority"], -x["moved"]))
    return items


def propose(db, user, horizon_days: int = 7) -> dict:
    """Build a plan. Returns intents plus a human explanation of each choice."""
    capacity = ctx_mod._capacity(db, user, days=horizon_days)["days"]
    budget = {d["date"]: int(d["free_minutes"] * USABLE_FRACTION) for d in capacity}
    by_offset = {i: d["date"] for i, d in enumerate(capacity)}

    items = _work_items(db, user, horizon_days)
    intents, explained, unplaceable = [], [], []

    # Work blocks JOCasta has already booked, so a second "plan my week" does
    # not stack duplicate blocks on top of the first.
    already_booked = {
        (t.title or "").removeprefix("Work on: ").strip().lower()
        for t in db.query(Task).filter(Task.user_id == user.id, Task.status == "open",
                                       Task.meta == "Planned by JOCasta").all()
    }

    for item in items:
        minutes = item["minutes"]
        placed_offset, slot = None, None

        if item["kind"] != "revision":
            if item["external_deadline"]:
                if item["title"].strip().lower() in already_booked:
                    continue                    # work for this is already booked
            elif not item["overdue"] and item["due_at"] is not None:
                continue                        # a dated personal task is already scheduled

        # Overdue work has no future deadline left to respect, so it takes the
        # *earliest* day with room — the point is to catch up. Everything else
        # takes the latest day whose block still finishes before the deadline,
        # which keeps the nearest days free for whatever arrives next.
        order = sorted(by_offset) if item["overdue"] else sorted(by_offset, reverse=True)
        for offset in order:
            when = _slot_datetime(offset)
            if when < now() - timedelta(hours=1):
                continue                                  # already in the past
            if not item["overdue"] and item["due_at"] is not None \
                    and when + timedelta(minutes=minutes) > item["due_at"]:
                continue                                  # wouldn't finish in time
            if budget.get(by_offset[offset], 0) < minutes:
                continue                                  # no room that day
            placed_offset, slot = offset, when
            break

        if placed_offset is None:
            unplaceable.append({
                "title": item["title"],
                "why": "no day in this window has enough free time"})
            continue

        budget[by_offset[placed_offset]] -= minutes
        day_label = (local_today() + timedelta(days=placed_offset)).strftime("%a %d %b")

        if item["kind"] == "revision":
            intents.append({"tool": "schedule_study",
                            "args": {"topic": item["title"], "due_at": slot.isoformat(),
                                     "minutes": minutes}})
            why = f"revision ahead of {item.get('because', 'an exam')}"

        elif item["external_deadline"]:
            # Never move a real deadline. Book the work before it instead.
            intents.append({"tool": "create_task",
                            "args": {"title": f"Work on: {item['title']}",
                                     "category": item.get("category") or "College",
                                     "due_at": slot.isoformat(), "est_minutes": minutes,
                                     "priority": "high" if item["overdue"] else "med",
                                     "meta": "Planned by JOCasta"}})
            why = ("overdue — booking catch-up time now" if item["overdue"]
                   else f"deadline {item['due_at'].date().isoformat()} is fixed — "
                        f"booking the work before it")

        else:
            if not item["overdue"] and item["due_at"] and \
                    abs((item["due_at"] - slot).total_seconds()) < 3600:
                continue                                   # already where it belongs
            intents.append({"tool": "reschedule_task",
                            "args": {"task_id": item["id"], "due_at": slot.isoformat()}})
            why = ("overdue — pulling it forward" if item["overdue"]
                   else "moving it to a day with room")

        explained.append({
            "title": item["title"], "kind": item["kind"], "when": slot.isoformat(),
            "minutes": minutes, "day": day_label, "why": why,
        })

    return {
        "intents": intents,
        "plan": explained,
        "unplaceable": unplaceable,
        "capacity": capacity,
        "horizon_days": horizon_days,
    }


def narrate(result: dict) -> str:
    """Explain the plan in one paragraph the user can act on."""
    plan, stuck = result["plan"], result["unplaceable"]
    if not plan and not stuck:
        return "Your schedule already looks balanced — nothing needs moving."
    lines = []
    if plan:
        lines.append(f"Here's how I'd lay out the next {result['horizon_days']} days:")
        for p in plan[:10]:
            lines.append(f"  • {p['day']} — {p['title']} ({p['minutes']} min): {p['why']}")
        if len(plan) > 10:
            lines.append(f"  • …and {len(plan) - 10} more")
    if stuck:
        lines.append("I couldn't place: " +
                     "; ".join(f"{u['title']} ({u['why']})" for u in stuck[:5]))
    return "\n".join(lines)

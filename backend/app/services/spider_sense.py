"""Spider Sense: backend-derived proactive intelligence.

A signal earns its place by answering three questions: what did I notice, why
does that matter, and what is the one useful thing to do about it. Anything that
cannot answer all three is noise, and noise is what makes people stop reading
their notifications.

Design notes
------------
* **Detectors are pure.** Each returns `Signal` objects; none of them touch the
  database beyond reading. Persistence happens once, in `_persist`.
* **One round trip.** Existing notifications are loaded once per scan and
  matched in memory. The previous implementation issued a SELECT per candidate
  signal, which meant a scan got slower every time a user accumulated data — on
  a page that runs a scan on every load.
* **Same numbers as the screen.** Budget and goal detectors call the very
  services the UI renders, so a warning in the tray can never contradict the
  page it points at.
* **Bounded.** `MAX_ACTIVE_SIGNALS` caps what a single scan will raise, most
  severe first.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from app.models import (Task, Assignment, Class, Course, Exam, AcademicEvent, Notification,
                        Project, LearningTopic, Application, Internship, Goal, Habit)
from app.services.timeutils import now, hours_until, local_today
from app.services import finance as finance_svc

LEVELS = ["info", "attention", "action", "spider_sense", "critical"]
SEVERITY = {"info": 1, "attention": 2, "action": 3, "spider_sense": 4, "critical": 5}

ATTENDANCE_FLOOR = 75          # percent — below this a course is at risk
REVISION_STALE_DAYS = 7        # a "needs revision" topic untouched this long
COLLISION_WINDOW_HOURS = 48    # two heavy deadlines this close collide
OVERLOAD_RATIO = 0.85          # committed vs available time before a day is overloaded
STREAK_AT_RISK = 3             # protect a streak at least this long
MAX_ACTIVE_SIGNALS = 25


@dataclass
class Signal:
    key: str                    # stable identity; makes scans idempotent
    level: str
    title: str
    explanation: str
    kind: str
    module: str
    source: str
    action_label: str = ""
    action_href: str = ""
    ref_type: str = ""
    ref_id: object = None

    @property
    def severity(self) -> int:
        return SEVERITY.get(self.level, 2)


def _hhmm_to_minutes(s: str) -> int:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


# ---------------------------------------------------------------- detectors
def _detect_deadlines(db, user) -> list[Signal]:
    out = []
    for a in db.query(Assignment).filter(Assignment.user_id == user.id,
                                         Assignment.status == "open").all():
        h = hours_until(a.due_at)
        if h < 0:
            out.append(Signal(
                key=f"overdue:{a.id}", level="action", kind="overdue", module="college",
                source="deadlines", ref_type="assignment", ref_id=a.id,
                title=f"{a.title} is overdue.",
                explanation=f"It was due {round(-h / 24, 1)} days ago and is still open.",
                action_label="Plan catch-up time", action_href="/planner"))
        elif h <= 36:
            out.append(Signal(
                key=f"deadline:{a.id}", level="action", kind="deadline", module="college",
                source="deadlines", ref_type="assignment", ref_id=a.id,
                title=f"{a.title} due within 36 hours.",
                explanation=f"About {round(h)}h left and roughly {a.est_minutes} minutes of work.",
                action_label="Block out the time", action_href="/planner"))
    return out


def _detect_collisions(db, user) -> list[Signal]:
    """Two significant deadlines landing close together.

    Individually each is manageable; together they are the thing that actually
    catches students out, and neither deadline detector would ever mention it.
    """
    items = []
    for a in db.query(Assignment).filter(Assignment.user_id == user.id,
                                         Assignment.status == "open").all():
        h = hours_until(a.due_at)
        if 0 <= h <= 24 * 10 and (a.est_minutes or 0) >= 45:
            items.append((h, a.title, a.est_minutes, "assignment"))
    for e in db.query(Exam).filter(Exam.user_id == user.id).all():
        h = hours_until(e.date)
        if 0 <= h <= 24 * 10:
            items.append((h, e.title, 180, "exam"))

    items.sort()
    out = []
    for i in range(len(items) - 1):
        (h1, t1, m1, _k1), (h2, t2, m2, _k2) = items[i], items[i + 1]
        if h2 - h1 <= COLLISION_WINDOW_HOURS:
            lo, hi = sorted([t1, t2])
            out.append(Signal(
                key=f"collision:{lo}:{hi}", level="action", kind="collision",
                module="planner", source="collisions",
                title=f"{t1} and {t2} land within {round(h2 - h1)}h of each other.",
                explanation=(f"That's about {round((m1 + m2) / 60, 1)}h of work "
                             f"converging in the same window."),
                action_label="Plan the week", action_href="/planner"))
            break   # one collision warning is enough; more is noise
    return out


def _detect_overload(db, user) -> list[Signal]:
    """A day already committed past what is realistically available."""
    from app.jocasta import context as ctx_mod
    out = []
    for day in ctx_mod._capacity(db, user, days=5)["days"]:
        available = day["class_minutes"] + day["committed_minutes"] + day["free_minutes"]
        if available <= 0:
            continue
        used = (day["class_minutes"] + day["committed_minutes"]) / available
        if used >= OVERLOAD_RATIO:
            out.append(Signal(
                key=f"overload:{day['date']}", level="attention", kind="overload",
                module="planner", source="capacity",
                title=f"{day['weekday']} is over-committed.",
                explanation=(f"{round((day['class_minutes'] + day['committed_minutes']) / 60, 1)}h "
                             f"of classes and tasks with only "
                             f"{round(day['free_minutes'] / 60, 1)}h left."),
                action_label="Rebalance the day", action_href="/planner"))
    return out[:2]


def _detect_postponed(db, user) -> list[Signal]:
    out = []
    for t in db.query(Task).filter(Task.user_id == user.id, Task.status == "open").all():
        if (t.postpone_count or 0) >= 2:
            out.append(Signal(
                key=f"postponed:{t.id}", level="attention", kind="postponed",
                module="tasks", source="avoidance", ref_type="task", ref_id=t.id,
                title=f"You've moved “{t.title}” {t.postpone_count} times.",
                explanation="Work that keeps slipping usually needs a smaller first step "
                            "or a better slot, not another postponement.",
                action_label="Find it a real slot", action_href="/planner"))
    return out


def _detect_exams(db, user) -> list[Signal]:
    out = []
    for ev in db.query(AcademicEvent).filter(AcademicEvent.user_id == user.id,
                                             AcademicEvent.type == "exam_window").all():
        if 0 <= hours_until(ev.date) <= 24 * 7:
            out.append(Signal(
                key=f"event:{ev.id}", level="attention", kind="event", module="college",
                source="calendar", ref_type="academic_event", ref_id=ev.id,
                title=f"Exam window approaching: {ev.title}.",
                explanation="Revision started now is worth more than revision started later.",
                action_label="Schedule revision", action_href="/learning"))
    for ex in db.query(Exam).filter(Exam.user_id == user.id).all():
        h = hours_until(ex.date)
        if 0 <= h <= 24 * 5:
            out.append(Signal(
                key=f"exam:{ex.id}", level="action", kind="exam", module="college",
                source="calendar", ref_type="exam", ref_id=ex.id,
                title=f"{ex.title} in {max(1, round(h / 24))} day(s).",
                explanation=f"Scheduled for {ex.date.date().isoformat()}"
                            + (f" in {ex.room}." if ex.room else "."),
                action_label="Plan revision", action_href="/planner"))
    return out


def _detect_attendance(db, user) -> list[Signal]:
    """Courses whose attendance has actually fallen below the floor.

    A course with no classes held yet sits at 0% because nothing has happened,
    not because anything is wrong. Warning about that would be noise the user
    cannot act on, so it is skipped until there is real attendance data.
    """
    from app.services import courses as course_svc
    out = []
    for c in db.query(Course).filter(Course.user_id == user.id).all():
        held = c.total_classes or 0
        if held <= 0:
            continue
        current = course_svc.pct(c.attended_classes, held)
        if current >= ATTENDANCE_FLOOR:
            continue
        gap = ATTENDANCE_FLOOR - current
        out.append(Signal(
            key=f"attendance:{c.id}", level="action", kind="attendance",
            module="college", source="attendance", ref_type="course", ref_id=c.id,
            title=f"{c.name} attendance is {current}%.",
            explanation=(f"{c.attended_classes or 0} of {held} classes attended — "
                         f"{gap} points below the {ATTENDANCE_FLOOR}% floor."),
            action_label="Review attendance", action_href="/college"))
    return out


def _detect_budgets(db, user) -> list[Signal]:
    out = []
    for b in finance_svc.budget_status(db, user):
        if b["state"] == "over":
            out.append(Signal(
                key=f"budget-over:{b['id']}", level="action", kind="budget",
                module="finance", source="budgets",
                title=f"{b['category']} budget is spent.",
                explanation=f"{b['spent']:.0f} of a {b['limit']:.0f} cap — {b['pct']}% used "
                            "with the month still running.",
                action_label="Review spending", action_href="/finance"))
        elif b["state"] == "near":
            out.append(Signal(
                key=f"budget-near:{b['id']}", level="attention", kind="budget",
                module="finance", source="budgets",
                title=f"{b['category']} is at {b['pct']}% of its cap.",
                explanation=f"{b['spent']:.0f} of {b['limit']:.0f} spent so far this month.",
                action_label="Check the category", action_href="/finance"))
    return out


def _detect_career(db, user) -> list[Signal]:
    out = []
    for app_row in db.query(Application).filter(Application.user_id == user.id).all():
        if app_row.stage == "result":
            continue
        it = db.query(Internship).filter(Internship.id == app_row.internship_id).first()
        if not it:
            continue
        if app_row.deadline:
            h = hours_until(app_row.deadline)
            if 0 <= h <= 72:
                out.append(Signal(
                    key=f"career:{app_row.id}", level="action", kind="career",
                    module="career", source="applications",
                    ref_type="application", ref_id=app_row.id,
                    title=f"{it.company} — {app_row.stage.upper()} due in {max(1, round(h))}h.",
                    explanation=f"{it.role} at {it.company}. Missing this closes the application.",
                    action_label="Open the application", action_href="/career"))
        if app_row.stage == "interview":
            out.append(Signal(
                key=f"career-stage:{app_row.id}", level="attention", kind="career",
                module="career", source="applications",
                ref_type="application", ref_id=app_row.id,
                title=f"{it.company} interview stage is live.",
                explanation="Prep time is worth scheduling while the stage is open.",
                action_label="Block prep time", action_href="/planner"))
    return out


def _detect_revision(db, user) -> list[Signal]:
    out = []
    for tp in db.query(LearningTopic).filter(LearningTopic.user_id == user.id,
                                             LearningTopic.state == "needs_revision").all():
        last = tp.last_reviewed_at
        stale_days = REVISION_STALE_DAYS if last is None else round(-hours_until(last) / 24)
        if last is None or stale_days >= REVISION_STALE_DAYS:
            out.append(Signal(
                key=f"revision:{tp.id}", level="attention", kind="revision",
                module="learning", source="learning", ref_type="topic", ref_id=tp.id,
                title=f"{tp.name} is flagged for revision.",
                explanation=("You marked it as needing work and haven't logged a session since."
                             if last is None else
                             f"No study logged on it for {stale_days} days."),
                action_label="Schedule a session", action_href="/learning"))
    return out


def _detect_projects(db, user) -> list[Signal]:
    out = []
    for p in db.query(Project).filter(Project.user_id == user.id,
                                      Project.status == "Active").all():
        if not p.due_at:
            continue
        h = hours_until(p.due_at)
        if h < 0:
            out.append(Signal(
                key=f"project-late:{p.id}", level="action", kind="deadline",
                module="projects", source="projects", ref_type="project", ref_id=p.id,
                title=f"Project {p.name} is past its target date.",
                explanation=f"Still at {p.completion}% complete.",
                action_label="Re-plan the project", action_href="/projects"))
        elif h <= 24 * 7:
            days = max(1, round(h / 24))
            # Only worth raising if progress and time left actually disagree.
            if p.completion < 100 - (days * 8):
                out.append(Signal(
                    key=f"project:{p.id}", level="attention", kind="deadline",
                    module="projects", source="projects", ref_type="project", ref_id=p.id,
                    title=f"{p.name} targets {days} day(s) out at {p.completion}%.",
                    explanation=f"At the current rate the remaining {100 - p.completion}% "
                                f"won't fit into {days} day(s).",
                    action_label="Open the project", action_href="/projects"))
    return out


def _detect_goals(db, user) -> list[Signal]:
    from app.services import goals as goals_svc
    out = []
    for g in db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").all():
        if not g.target_date:
            continue
        h = hours_until(g.target_date)
        if 0 <= h <= 24 * 14:
            pct = goals_svc.detail(db, user, g)["progress"]
            days = max(1, round(h / 24))
            if pct < 70:
                out.append(Signal(
                    key=f"goal:{g.id}", level="attention", kind="goal", module="goals",
                    source="goals", ref_type="goal", ref_id=g.id,
                    title=f"“{g.title}” is {pct}% done with {days} day(s) left.",
                    explanation="Progress is read from the work linked to this goal — "
                                "linking more work, or moving the date, would both help.",
                    action_label="Review the goal", action_href="/goals"))
    return out


def _detect_habits(db, user) -> list[Signal]:
    """A streak worth protecting that hasn't been logged today."""
    from app.services import habits as habits_svc
    out = []
    for h in habits_svc.summary(db, user):
        if h["done_today"] or h["streak"] < STREAK_AT_RISK:
            continue
        out.append(Signal(
            key=f"habit:{h['id']}", level="info", kind="habit", module="personal",
            source="habits",
            title=f"{h['title']} — {h['streak']} day streak not logged yet.",
            explanation=f"You're at {h['done_this_week']}/{h['target_per_week']} this week.",
            action_label="Log it", action_href="/personal"))
    return out[:3]


def _detect_conflicts(db, uid) -> list[tuple[str, str]]:
    """Overlapping items today. Kept as (key, title) pairs because the Planner
    endpoint renders these directly as well."""
    out = []
    windows = []
    today = local_today()

    for ev in db.query(AcademicEvent).filter(AcademicEvent.user_id == uid,
                                             AcademicEvent.type == "event").all():
        if ev.date and ev.end_date and ev.date.date() == today:
            windows.append((ev.date.hour * 60 + ev.date.minute,
                            ev.end_date.hour * 60 + ev.end_date.minute, ev.title))

    rows = (db.query(Class, Course).join(Course, Class.course_id == Course.id)
            .filter(Class.user_id == uid, Class.day_of_week == today.weekday()).all())
    for cl, c in rows:
        windows.append((_hhmm_to_minutes(cl.start_time), _hhmm_to_minutes(cl.end_time), c.name))

    for i in range(len(windows)):
        for j in range(i + 1, len(windows)):
            a, b = windows[i], windows[j]
            if a[0] < b[1] and b[0] < a[1] and a[2] != b[2]:
                lo, hi = sorted([a[2], b[2]])
                out.append((f"conflict:{lo}:{hi}", f"{a[2]} overlaps with {b[2]} today."))
    return out


def _detect_schedule_conflicts(db, user) -> list[Signal]:
    return [Signal(key=key, level="critical", kind="conflict", module="planner",
                   source="timetable", title=title,
                   explanation="Two things are booked over the same period today — "
                               "one of them needs to move.",
                   action_label="Resolve the clash", action_href="/planner")
            for key, title in _detect_conflicts(db, user.id)]


DETECTORS = (
    _detect_schedule_conflicts, _detect_deadlines, _detect_collisions, _detect_overload,
    _detect_exams, _detect_attendance, _detect_budgets, _detect_career,
    _detect_revision, _detect_projects, _detect_goals, _detect_postponed, _detect_habits,
)


# ---------------------------------------------------------------- persistence
def _persist(db, user, signals: list[Signal]) -> list[Notification]:
    """Reconcile detected signals with stored ones in a single round trip.

    Loading every notification once and matching in memory is what keeps a scan
    O(1) queries instead of O(number of signals) — this runs on nearly every
    page load, so the difference compounds.
    """
    signals = sorted(signals, key=lambda s: -s.severity)[:MAX_ACTIVE_SIGNALS]
    existing = {n.dedupe_key: n for n in
                db.query(Notification).filter(Notification.user_id == user.id).all()}

    touched = []
    for sig in signals:
        n = existing.get(sig.key)
        if n is None:
            n = Notification(user_id=user.id, dedupe_key=sig.key)
            db.add(n)
            existing[sig.key] = n
        # Refresh the wording every scan: the same signal says something
        # different when a deadline moves from 30h away to 6h away.
        n.level, n.title, n.kind, n.module = sig.level, sig.title, sig.kind, sig.module
        n.explanation, n.source, n.severity = sig.explanation, sig.source, sig.severity
        n.action_label, n.action_href = sig.action_label, sig.action_href
        n.ref_type, n.ref_id = sig.ref_type, sig.ref_id
        touched.append(n)

    # A condition that no longer holds should stop nagging.
    live = {s.key for s in signals}
    for key, n in existing.items():
        if key not in live and not n.resolved:
            n.resolved = True

    db.commit()
    return touched


def scan(db, user) -> list[Notification]:
    signals: list[Signal] = []
    for detector in DETECTORS:
        try:
            signals.extend(detector(db, user))
        except Exception:
            # One failing detector must not blind all the others.
            import logging
            logging.getLogger("express.spider_sense").exception(
                "detector failed: %s", getattr(detector, "__name__", "?"))
    return _persist(db, user, signals)


def active(db, user) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id,
                Notification.acknowledged == False,  # noqa: E712
                Notification.resolved == False)  # noqa: E712
        .order_by(Notification.severity.desc(), Notification.created_at.desc())
        .all()
    )

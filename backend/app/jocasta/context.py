"""User context for JOCasta.

The model never receives the database. It receives a *bounded, targeted* view
assembled here: a handful of slices, each capped, each already scoped to the
authenticated user, each traceable back to the service the UI reads.

Three rules this module exists to enforce:

  1. **Targeted, not exhaustive.** `select_slices` picks only the slices the
     message plausibly needs. Asking "what's due?" should not ship the user's
     budget and habit history to a model.
  2. **Bounded.** Every slice caps its rows. Context size stays roughly constant
     as a user accumulates years of data.
  3. **Explainable.** `build()` reports which slices it included and why, so a
     surprising answer can be traced to the context that produced it.
"""
from datetime import timedelta

from app.models import (Task, Assignment, Exam, Class, Course, Project, ProjectTask,
                        LearningTopic, Goal, Habit, Internship, Application, Memory,
                        Notification, AcademicEvent)
from app.services import (finance as finance_svc, goals as goals_svc,
                          habits as habits_svc, spider_sense)
from app.services.timeutils import (now, local_now, local_today, start_of_local_day,
                                    hours_until, as_utc)

# Row caps. Generous enough to reason with, small enough to stay cheap.
CAP = 12
HORIZON_DAYS = 14


def _iso(dt):
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------- slices
def _today(db, user) -> dict:
    start = start_of_local_day(0)
    end = start + timedelta(days=1)
    dow = local_today().weekday()
    classes = (db.query(Class, Course).join(Course, Class.course_id == Course.id)
               .filter(Class.user_id == user.id, Class.day_of_week == dow)
               .order_by(Class.start_time).all())
    tasks = (db.query(Task)
             .filter(Task.user_id == user.id, Task.status == "open",
                     Task.due_at >= start, Task.due_at < end)
             .order_by(Task.due_at).limit(CAP).all())
    return {
        "date": local_today().isoformat(),
        "classes": [{"course": c.name, "start": cl.start_time, "end": cl.end_time}
                    for cl, c in classes],
        "tasks": [{"id": str(t.id), "title": t.title, "at": _iso(t.due_at),
                   "minutes": t.est_minutes, "priority": t.priority} for t in tasks],
    }


def _deadlines(db, user) -> dict:
    horizon = now() + timedelta(days=HORIZON_DAYS)
    assigns = (db.query(Assignment)
               .filter(Assignment.user_id == user.id, Assignment.status == "open",
                       Assignment.due_at <= horizon)
               .order_by(Assignment.due_at).limit(CAP).all())
    exams = (db.query(Exam)
             .filter(Exam.user_id == user.id, Exam.date >= now(), Exam.date <= horizon)
             .order_by(Exam.date).limit(CAP).all())
    projects = (db.query(Project)
                .filter(Project.user_id == user.id, Project.status == "Active",
                        Project.due_at.isnot(None), Project.due_at <= horizon)
                .order_by(Project.due_at).limit(CAP).all())
    apps = (db.query(Application, Internship)
            .join(Internship, Application.internship_id == Internship.id)
            .filter(Application.user_id == user.id, Application.deadline.isnot(None),
                    Application.deadline <= horizon, Application.stage != "result")
            .order_by(Application.deadline).limit(CAP).all())
    return {
        "horizon_days": HORIZON_DAYS,
        "assignments": [{"id": str(a.id), "title": a.title, "due": _iso(a.due_at),
                         "hours_away": round(hours_until(a.due_at), 1),
                         "minutes_of_work": a.est_minutes, "priority": a.priority}
                        for a in assigns],
        "exams": [{"title": e.title, "date": _iso(e.date),
                   "hours_away": round(hours_until(e.date), 1)} for e in exams],
        "projects": [{"name": p.name, "due": _iso(p.due_at), "completion": p.completion,
                      "open_tasks": db.query(ProjectTask).filter(
                          ProjectTask.project_id == p.id,
                          ProjectTask.status == "open").count()} for p in projects],
        "applications": [{"company": i.company, "stage": a.stage, "due": _iso(a.deadline)}
                         for a, i in apps],
    }


def _overdue(db, user) -> dict:
    rows = (db.query(Task)
            .filter(Task.user_id == user.id, Task.status == "open",
                    Task.due_at.isnot(None), Task.due_at < now())
            .order_by(Task.due_at).limit(CAP).all())
    return {"count": len(rows),
            "tasks": [{"id": str(t.id), "title": t.title, "was_due": _iso(t.due_at),
                       "days_late": max(0, round(-hours_until(t.due_at) / 24, 1)),
                       "moved_times": t.postpone_count or 0} for t in rows]}


def _capacity(db, user, days: int = 7) -> dict:
    """How committed each of the next `days` days already is.

    Class time comes from the timetable; task time from estimates. This is what
    lets JOCasta answer "when could I actually do this?" instead of guessing.

    Both sides are fetched once and bucketed in memory. Querying per day made
    this O(days) round trips on a function that runs inside every planning
    request *and* the overload detector, which runs on every page load.
    """
    WAKING = 14 * 60          # a realistic student working day, not 24h
    window_start = start_of_local_day(0)
    window_end = start_of_local_day(days)

    # class minutes per weekday, computed once
    class_minutes: dict[int, int] = {}
    for cl, _c in (db.query(Class, Course).join(Course, Class.course_id == Course.id)
                   .filter(Class.user_id == user.id).all()):
        try:
            sh, sm = (int(x) for x in cl.start_time.split(":"))
            eh, em = (int(x) for x in cl.end_time.split(":"))
            minutes = max(0, (eh * 60 + em) - (sh * 60 + sm))
        except Exception:
            continue
        class_minutes[cl.day_of_week] = class_minutes.get(cl.day_of_week, 0) + minutes

    # Local-day boundaries as UTC instants, so bucketing needs no tz maths.
    bounds = [(offset, start_of_local_day(offset), start_of_local_day(offset + 1))
              for offset in range(days)]
    committed: dict[int, int] = {}
    for t in (db.query(Task)
              .filter(Task.user_id == user.id, Task.status == "open",
                      Task.due_at >= window_start, Task.due_at < window_end).all()):
        due = as_utc(t.due_at)
        for offset, lo, hi in bounds:
            if lo <= due < hi:
                committed[offset] = committed.get(offset, 0) + (t.est_minutes or 0)
                break

    out = []
    for offset in range(days):
        d = local_today() + timedelta(days=offset)
        cls = class_minutes.get(d.weekday(), 0)
        tasks = committed.get(offset, 0)
        out.append({"date": d.isoformat(), "weekday": d.strftime("%a"),
                    "class_minutes": cls, "committed_minutes": tasks,
                    "free_minutes": max(0, WAKING - cls - tasks)})
    return {"days": out}


def _projects(db, user) -> dict:
    rows = (db.query(Project).filter(Project.user_id == user.id)
            .order_by(Project.priority).limit(CAP).all())
    return {"projects": [{"id": str(p.id), "name": p.name, "status": p.status,
                          "phase": p.phase, "completion": p.completion,
                          "due": _iso(p.due_at)} for p in rows]}


def _learning(db, user) -> dict:
    rows = (db.query(LearningTopic).filter(LearningTopic.user_id == user.id)
            .limit(CAP * 2).all())
    return {"topics": [{"id": str(t.id), "name": t.name, "area": t.area,
                        "state": t.state, "progress": t.progress,
                        "last_reviewed": _iso(t.last_reviewed_at)} for t in rows],
            "needs_revision": [t.name for t in rows if t.state == "needs_revision"]}


def _goals(db, user) -> dict:
    rows = [g for g in goals_svc.listing(db, user) if g["status"] == "active"][:CAP]
    return {"goals": [{"id": g["id"], "title": g["title"], "progress": g["progress"],
                       "target_date": g["target_date"], "category": g["category"]}
                      for g in rows]}


def _habits(db, user) -> dict:
    rows = habits_svc.summary(db, user)[:CAP]
    return {"habits": [{"id": h["id"], "title": h["title"], "streak": h["streak"],
                        "done_today": h["done_today"],
                        "this_week": f"{h['done_this_week']}/{h['target_per_week']}"}
                       for h in rows]}


def _finance(db, user) -> dict:
    s = finance_svc.summary(db, user)
    return {"month_spent": s["month_spent"], "month_income": s["month_income"],
            "net": s["net"],
            "budgets": [b for b in s["budgets"] if b["state"] != "ok"][:CAP] or s["budgets"][:4]}


def _career(db, user) -> dict:
    rows = (db.query(Application, Internship)
            .join(Internship, Application.internship_id == Internship.id)
            .filter(Application.user_id == user.id).limit(CAP).all())
    return {"applications": [{"company": i.company, "role": i.role, "stage": a.stage,
                              "deadline": _iso(a.deadline)} for a, i in rows]}


def _memory(db, user, keywords: list[str] | None = None) -> dict:
    """Selective recall.

    Pinned memories are always relevant. Beyond those, only memories matching a
    keyword from the message are included — dumping the whole store into every
    prompt is what the Memory module exists to avoid.
    """
    pinned = (db.query(Memory).filter(Memory.user_id == user.id, Memory.pinned == True)  # noqa: E712
              .limit(CAP // 2).all())
    matched = []
    for kw in (keywords or [])[:5]:
        if len(kw) < 4:
            continue
        matched += (db.query(Memory)
                    .filter(Memory.user_id == user.id, Memory.text.ilike(f"%{kw}%"))
                    .limit(4).all())
    seen, rows = set(), []
    for m in pinned + matched:
        if m.id in seen:
            continue
        seen.add(m.id)
        rows.append({"text": m.text, "category": m.category})
    return {"memories": rows[:CAP]}


def _signals(db, user) -> dict:
    rows = spider_sense.active(db, user)[:CAP]
    return {"signals": [{"id": str(n.id), "level": n.level, "title": n.title,
                         "module": n.module, "kind": n.kind} for n in rows]}


SLICES = {
    "today": _today, "deadlines": _deadlines, "overdue": _overdue, "capacity": _capacity,
    "projects": _projects, "learning": _learning, "goals": _goals, "habits": _habits,
    "finance": _finance, "career": _career, "memory": _memory, "signals": _signals,
}

# Keyword -> slices. A message mentioning none of these gets PLANNING_CORE.
TRIGGERS = {
    "today": ("today", "now", "schedule", "class", "morning", "tonight"),
    "deadlines": ("due", "deadline", "exam", "test", "submit", "assignment", "friday",
                  "monday", "week", "plan", "prepare", "revise"),
    "overdue": ("overdue", "late", "behind", "missed", "catch up"),
    "capacity": ("plan", "when", "time", "fit", "free", "busy", "schedule", "squeeze"),
    "projects": ("project", "build", "ship", "repo", "phase"),
    "learning": ("study", "learn", "revise", "topic", "practice", "dsa", "understand"),
    "goals": ("goal", "target", "aim", "objective"),
    "habits": ("habit", "streak", "routine", "daily"),
    "finance": ("spend", "spent", "budget", "money", "cost", "expense", "afford"),
    "career": ("intern", "job", "application", "interview", "placement", "oa"),
    "signals": ("wrong", "worry", "risk", "urgent", "problem", "attention", "behind"),
}

# What a planning question needs when nothing more specific is implied.
PLANNING_CORE = ("today", "deadlines", "overdue", "capacity", "signals")


def select_slices(text: str) -> list[str]:
    """Pick the slices this message plausibly needs, plus memory (always, but
    keyword-filtered) — targeted retrieval rather than a full dump."""
    t = (text or "").lower()
    chosen = {name for name, words in TRIGGERS.items() if any(w in t for w in words)}
    if not chosen:
        chosen = set(PLANNING_CORE)
    chosen.add("memory")
    return sorted(chosen)


def build(db, user, text: str = "", slices: list[str] | None = None) -> dict:
    """Assemble context. Returns the data plus the provenance of the selection."""
    names = slices if slices is not None else select_slices(text)
    keywords = [w.strip(".,?!\"'") for w in (text or "").lower().split() if len(w) > 3]

    data, included = {}, []
    for name in names:
        fn = SLICES.get(name)
        if not fn:
            continue
        data[name] = _memory(db, user, keywords) if name == "memory" else fn(db, user)
        included.append(name)

    return {
        "user": {"name": user.name, "id": str(user.id)},
        "as_of": _iso(now()),
        "included_slices": included,
        "reason": "selected from the message" if slices is None else "explicitly requested",
        **data,
    }


def summarize(ctx: dict) -> str:
    """A compact human/LLM-readable rendering. Kept short on purpose: the model
    reasons better over a tight brief than over raw JSON."""
    parts = []
    t = ctx.get("today")
    if t:
        cls = ", ".join(f"{c['course']} {c['start']}" for c in t["classes"]) or "no classes"
        tk = ", ".join(f"{x['title']} ({x['at'][11:16]})" for x in t["tasks"]) or "nothing scheduled"
        parts.append(f"TODAY ({t['date']}): {cls}. Tasks: {tk}.")

    d = ctx.get("deadlines")
    if d:
        bits = []
        for a in d["assignments"][:5]:
            bits.append(f"{a['title']} in {a['hours_away']}h ({a['minutes_of_work']}min of work)")
        for e in d["exams"][:3]:
            bits.append(f"EXAM {e['title']} in {round(e['hours_away'] / 24, 1)}d")
        for p in d["projects"][:3]:
            bits.append(f"project {p['name']} at {p['completion']}% due {p['due'][:10]}")
        for ap in d["applications"][:3]:
            bits.append(f"{ap['company']} {ap['stage']} due {ap['due'][:10]}")
        parts.append("UPCOMING: " + ("; ".join(bits) if bits else "nothing in the next two weeks") + ".")

    o = ctx.get("overdue")
    if o and o["count"]:
        parts.append("OVERDUE: " + "; ".join(
            f"{x['title']} ({x['days_late']}d late)" for x in o["tasks"][:5]) + ".")

    c = ctx.get("capacity")
    if c:
        parts.append("CAPACITY: " + ", ".join(
            f"{d['weekday']} {round(d['free_minutes'] / 60, 1)}h free" for d in c["days"][:7]) + ".")

    for key, label, fmt in [
        ("goals", "GOALS", lambda g: f"{g['title']} {g['progress']}%"),
        ("projects", "PROJECTS", lambda p: f"{p['name']} {p['completion']}%"),
        ("habits", "HABITS", lambda h: f"{h['title']} {h['streak']}d"),
    ]:
        section = ctx.get(key)
        if section:
            rows = section.get(key, [])[:5]
            if rows:
                parts.append(f"{label}: " + ", ".join(fmt(r) for r in rows) + ".")

    lr = ctx.get("learning")
    if lr and lr.get("needs_revision"):
        parts.append("NEEDS REVISION: " + ", ".join(lr["needs_revision"][:5]) + ".")

    f = ctx.get("finance")
    if f:
        over = [b["category"] for b in f["budgets"] if b.get("state") in ("near", "over")]
        parts.append(f"FINANCE: {f['month_spent']} spent this month"
                     + (f"; tight on {', '.join(over)}" if over else "") + ".")

    s = ctx.get("signals")
    if s and s["signals"]:
        parts.append("SIGNALS: " + "; ".join(x["title"] for x in s["signals"][:5]))

    m = ctx.get("memory")
    if m and m["memories"]:
        parts.append("REMEMBERED: " + "; ".join(x["text"] for x in m["memories"][:5]))

    return "\n".join(parts)

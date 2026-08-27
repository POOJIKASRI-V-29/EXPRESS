"""Authorized tool layer.

SECURITY (spec #8): JOCasta has NO database authority. Every function here
receives the *server-resolved* authenticated `user` and filters every query by
`user.id`. The AI can only ask for a tool by name + args; it never gets a db
session, never sees another user's rows, and cannot execute anything the
executor doesn't explicitly implement here.

Tools that take a human name ("the DBMS assignment", "Trees") resolve it with
`_match`, which only ever searches rows already scoped to this user — so a
fuzzy name can never reach someone else's data.
"""
from datetime import timedelta
from app.models import (Task, Reminder, Memory, Note, Assignment, Class, Course, Notification,
                        LearningTopic, LearningSession, Project, ProjectTask, Habit, HabitLog,
                        FinanceEntry, Budget, Goal, Internship, Application, Exam)
from app.services import materialize, spider_sense, habits as habits_svc, finance as finance_svc
from app.services import goals as goals_svc
from app.services.timeutils import now, local_today
from app.jocasta import schemas as sc


# ---------------------------------------------------------------- helpers
def _own_task(db, user, task_id):
    return db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()


def _match(rows, query: str, *fields):
    """Pick the row whose field best matches `query`. Exact (case-insensitive)
    wins, then containment, then a shared-word overlap. Returns None if nothing
    plausibly matches, so the tool fails loudly instead of guessing."""
    q = (query or "").strip().lower()
    if not q or not rows:
        return None
    def vals(r):
        return [str(getattr(r, f, "") or "").lower() for f in fields]
    for r in rows:
        if q in vals(r):
            return r
    for r in rows:
        if any(q in v or v in q for v in vals(r) if v):
            return r
    qwords = {w for w in q.split() if len(w) > 2}
    best, best_score = None, 0
    for r in rows:
        score = max((len(qwords & set(v.split())) for v in vals(r)), default=0)
        if score > best_score:
            best, best_score = r, score
    return best


def _user_rows(db, user, model):
    return db.query(model).filter(model.user_id == user.id).all()


# ---------------------------------------------------------------- tasks
def create_task(db, user, a: sc.CreateTaskArgs):
    t = Task(user_id=user.id, title=a.title, category=a.category, due_at=a.due_at,
             priority=a.priority, est_minutes=a.est_minutes, icon=a.icon, meta=a.meta or a.category)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": str(t.id), "title": t.title, "category": t.category,
            "due_at": t.due_at.isoformat() if t.due_at else None}


def update_task(db, user, a: sc.UpdateTaskArgs):
    t = _own_task(db, user, a.task_id)
    if not t:
        raise ValueError("Task not found")
    for f in ("title", "priority", "status"):
        v = getattr(a, f)
        if v is not None:
            setattr(t, f, v)
    db.commit()
    return {"id": str(t.id), "status": t.status, "priority": t.priority}


def _complete(db, user, t: Task):
    t.status = "done"; t.completed_at = now()
    if t.assignment_id:
        asg = db.query(Assignment).filter(Assignment.id == t.assignment_id,
                                          Assignment.user_id == user.id).first()
        if asg:
            asg.status = "done"
    if t.project_task_id:
        pt = db.query(ProjectTask).filter(ProjectTask.id == t.project_task_id,
                                          ProjectTask.user_id == user.id).first()
        if pt:
            pt.status = "done"
    db.commit()
    return {"id": str(t.id), "title": t.title, "status": "done"}


def complete_task(db, user, a: sc.TaskIdArgs):
    t = _own_task(db, user, a.task_id)
    if not t:
        raise ValueError("Task not found")
    return _complete(db, user, t)


def complete_task_by_name(db, user, a: sc.CompleteByTitleArgs):
    """Complete the task the user described, without needing its id."""
    rows = db.query(Task).filter(Task.user_id == user.id, Task.status == "open").all()
    t = _match(rows, a.query, "title", "meta", "category")
    if not t:
        raise ValueError(f"no open task matching “{a.query}”")
    return _complete(db, user, t)


def reschedule_task(db, user, a: sc.RescheduleArgs):
    t = _own_task(db, user, a.task_id)
    if not t:
        raise ValueError("Task not found")
    t.due_at = a.due_at
    t.postpone_count = (t.postpone_count or 0) + 1
    if t.assignment_id:
        asg = db.query(Assignment).filter(Assignment.id == t.assignment_id,
                                          Assignment.user_id == user.id).first()
        if asg:
            asg.due_at = a.due_at
    db.commit()
    spider_sense.scan(db, user)  # deadline change -> Spider Sense re-derives
    return {"id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat(),
            "postpone_count": t.postpone_count}


def find_task(db, user, a: sc.FindTaskArgs):
    rows = db.query(Task).filter(Task.user_id == user.id, Task.status == "open").all()
    t = _match(rows, a.query, "title", "meta", "category")
    if not t:
        raise ValueError(f"no open task matching “{a.query}”")
    return {"id": str(t.id), "title": t.title,
            "due_at": t.due_at.isoformat() if t.due_at else None, "priority": t.priority}


def create_reminder(db, user, a: sc.CreateReminderArgs):
    r = Reminder(user_id=user.id, title=a.title, remind_at=a.remind_at, meta=a.meta)
    db.add(r)
    # a reminder also surfaces as a Task so it lands in Planner/Home
    t = Task(user_id=user.id, title=a.title, category="Personal", due_at=a.remind_at,
             icon="bell", meta="Reminder", source="reminder")
    db.add(t); db.commit(); db.refresh(r)
    return {"id": str(r.id), "title": r.title, "remind_at": r.remind_at.isoformat()}


# ---------------------------------------------------------------- memory
def save_memory(db, user, a: sc.SaveMemoryArgs):
    m = Memory(user_id=user.id, text=a.text, category=a.category, source="jocasta")
    db.add(m); db.commit(); db.refresh(m)
    return {"id": str(m.id), "text": m.text, "category": m.category, "saved": True}


def search_memory(db, user, a: sc.SearchMemoryArgs):
    q = f"%{a.query.lower()}%"
    rows = (db.query(Memory)
            .filter(Memory.user_id == user.id, Memory.text.ilike(q))
            .order_by(Memory.created_at.desc()).all())
    return [{"id": str(m.id), "text": m.text, "category": m.category} for m in rows]


def update_memory(db, user, a: sc.UpdateMemoryArgs):
    m = db.query(Memory).filter(Memory.id == a.memory_id, Memory.user_id == user.id).first()
    if not m:
        raise ValueError("Memory not found")
    for f in ("text", "category", "pinned"):
        v = getattr(a, f)
        if v is not None:
            setattr(m, f, v)
    db.commit()
    return {"id": str(m.id), "text": m.text, "category": m.category, "pinned": m.pinned}


def delete_memory(db, user, a: sc.MemoryIdArgs):
    m = db.query(Memory).filter(Memory.id == a.memory_id, Memory.user_id == user.id).first()
    if not m:
        raise ValueError("Memory not found")
    db.delete(m); db.commit()
    return {"deleted": True, "id": a.memory_id}


def get_memories(db, user, a: sc.EmptyArgs):
    rows = (db.query(Memory).filter(Memory.user_id == user.id)
            .order_by(Memory.created_at.desc()).all())
    return [{"id": str(m.id), "text": m.text, "category": m.category, "source": m.source}
            for m in rows]


# ---------------------------------------------------------------- notes
def create_note(db, user, a: sc.CreateNoteArgs):
    title = a.title or (a.body[:48] + ("…" if len(a.body) > 48 else ""))
    n = Note(user_id=user.id, title=title, body=a.body, tags=a.tags)
    db.add(n); db.commit(); db.refresh(n)
    return {"id": str(n.id), "title": n.title}


def search_notes(db, user, a: sc.SearchNotesArgs):
    like = f"%{a.query}%"
    rows = (db.query(Note).filter(Note.user_id == user.id)
            .filter(Note.title.ilike(like) | Note.body.ilike(like) | Note.tags.ilike(like))
            .order_by(Note.updated_at.desc()).all())
    return [{"id": str(n.id), "title": n.title, "body": n.body[:200]} for n in rows]


# ---------------------------------------------------------------- college
def create_assignment(db, user, a: sc.CreateAssignmentArgs):
    course = _match(_user_rows(db, user, Course), a.course or "", "name", "code") if a.course else None
    asg = Assignment(user_id=user.id, title=a.title, description=a.description,
                     due_at=a.due_at, est_minutes=a.est_minutes, priority=a.priority,
                     course_id=course.id if course else None)
    db.add(asg); db.flush()
    materialize.task_for_assignment(db, asg)
    db.commit()
    spider_sense.scan(db, user)
    return {"id": str(asg.id), "title": asg.title, "due_at": asg.due_at.isoformat(),
            "course": course.name if course else None}


def mark_attendance(db, user, a: sc.MarkAttendanceArgs):
    course = _match(_user_rows(db, user, Course), a.course, "name", "code")
    if not course:
        raise ValueError(f"no course matching “{a.course}”")
    slots = db.query(Class).filter(Class.user_id == user.id, Class.course_id == course.id).count() or 1
    step = max(1, round(100 / (slots * 15)))
    course.attendance = max(0, min(100, (course.attendance or 0) + (step if a.attended else -step)))
    db.commit()
    spider_sense.scan(db, user)
    return {"course": course.name, "attendance": course.attendance, "attended": a.attended}


def get_schedule(db, user, a: sc.EmptyArgs):
    dow = local_today().weekday()
    rows = (db.query(Class, Course)
            .join(Course, Class.course_id == Course.id)
            .filter(Class.user_id == user.id, Class.day_of_week == dow)
            .order_by(Class.start_time).all())
    return [{"course": c.name, "start": cl.start_time, "end": cl.end_time, "room": cl.room}
            for cl, c in rows]


def get_college(db, user, a: sc.EmptyArgs):
    courses = _user_rows(db, user, Course)
    exams = (db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.date).all())
    return {
        "attendance": round(sum(c.attendance for c in courses) / len(courses)) if courses else 0,
        "courses": [{"name": c.name, "attendance": c.attendance} for c in courses],
        "at_risk": [c.name for c in courses if (c.attendance or 0) < spider_sense.ATTENDANCE_FLOOR],
        "next_exam": None if not exams else {"title": exams[0].title, "date": exams[0].date.isoformat()},
    }


# ---------------------------------------------------------------- learning
def log_study(db, user, a: sc.LogStudyArgs):
    topic = _match(_user_rows(db, user, LearningTopic), a.topic, "name", "area")
    if not topic:
        raise ValueError(f"no topic matching “{a.topic}”")
    s = LearningSession(user_id=user.id, topic_id=topic.id, minutes=a.minutes,
                        note=a.note, started_at=now())
    db.add(s)
    topic.last_reviewed_at = now()
    topic.progress = min(100, (topic.progress or 0) + max(1, round(a.minutes / 10)))
    if topic.state == "not_started":
        topic.state = "learning"
    db.commit()
    spider_sense.scan(db, user)
    return {"topic": topic.name, "minutes": a.minutes, "progress": topic.progress}


def schedule_study(db, user, a: sc.ScheduleStudyArgs):
    topic = _match(_user_rows(db, user, LearningTopic), a.topic, "name", "area")
    if not topic:
        raise ValueError(f"no topic matching “{a.topic}”")
    t = materialize.task_for_topic(db, topic, a.due_at, a.minutes)
    db.commit(); db.refresh(t)
    return {"topic": topic.name, "task_id": str(t.id), "due_at": t.due_at.isoformat()}


def create_topic(db, user, a: sc.CreateTopicArgs):
    t = LearningTopic(user_id=user.id, name=a.name, area=a.area, state=a.state)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": str(t.id), "name": t.name, "area": t.area}


def get_learning(db, user, a: sc.EmptyArgs):
    topics = _user_rows(db, user, LearningTopic)
    sessions = _user_rows(db, user, LearningSession)
    return {
        "topics": [{"name": t.name, "area": t.area, "state": t.state, "progress": t.progress}
                   for t in topics],
        "needs_revision": [t.name for t in topics if t.state == "needs_revision"],
        "total_minutes": sum(s.minutes or 0 for s in sessions),
    }


# ---------------------------------------------------------------- projects
def create_project_task(db, user, a: sc.CreateProjectTaskArgs):
    project = _match(_user_rows(db, user, Project), a.project, "name", "stack")
    if not project:
        raise ValueError(f"no project matching “{a.project}”")
    pt = ProjectTask(user_id=user.id, project_id=project.id, title=a.title, due_at=a.due_at)
    db.add(pt); db.flush()
    materialize.task_for_project_task(db, pt)
    db.commit()
    return {"project": project.name, "title": pt.title,
            "due_at": pt.due_at.isoformat() if pt.due_at else None}


def get_projects(db, user, a: sc.EmptyArgs):
    rows = _user_rows(db, user, Project)
    return [{"name": p.name, "status": p.status, "phase": p.phase, "completion": p.completion}
            for p in rows]


# ---------------------------------------------------------------- personal
def log_habit(db, user, a: sc.LogHabitArgs):
    h = _match(_user_rows(db, user, Habit), a.habit, "title")
    if not h:
        raise ValueError(f"no habit matching “{a.habit}”")
    today = local_today()
    existing = (db.query(HabitLog)
                .filter(HabitLog.user_id == user.id, HabitLog.habit_id == h.id,
                        HabitLog.on_date == today).first())
    if existing:
        return {"habit": h.title, "streak": h.streak, "already_done": True}
    db.add(HabitLog(user_id=user.id, habit_id=h.id, on_date=today))
    db.flush()
    habits_svc.recompute(db, user, h)
    db.commit()
    return {"habit": h.title, "streak": h.streak, "already_done": False}


def create_habit(db, user, a: sc.CreateHabitArgs):
    h = Habit(user_id=user.id, title=a.title, cadence=a.cadence, target_per_week=a.target_per_week)
    db.add(h); db.commit(); db.refresh(h)
    return {"id": str(h.id), "title": h.title, "cadence": h.cadence}


def get_habits(db, user, a: sc.EmptyArgs):
    return habits_svc.summary(db, user)


# ---------------------------------------------------------------- finance
def log_expense(db, user, a: sc.LogExpenseArgs):
    e = FinanceEntry(user_id=user.id, amount=a.amount, category=a.category,
                     kind=a.kind, note=a.note, date=a.date or now())
    db.add(e); db.commit()
    spider_sense.scan(db, user)
    status = next((b for b in finance_svc.budget_status(db, user) if b["category"] == a.category), None)
    return {"amount": float(a.amount), "category": a.category, "kind": a.kind,
            "budget": status}


def set_budget(db, user, a: sc.SetBudgetArgs):
    b = (db.query(Budget)
         .filter(Budget.user_id == user.id, Budget.category == a.category).first())
    if b:
        b.monthly_limit = a.monthly_limit
    else:
        db.add(Budget(user_id=user.id, category=a.category, monthly_limit=a.monthly_limit))
    db.commit()
    spider_sense.scan(db, user)
    return {"category": a.category, "monthly_limit": float(a.monthly_limit)}


def get_finance(db, user, a: sc.EmptyArgs):
    s = finance_svc.summary(db, user)
    return {"month_spent": s["month_spent"], "month_income": s["month_income"],
            "net": s["net"], "budgets": s["budgets"], "by_category": s["by_category"][:5]}


# ---------------------------------------------------------------- goals
def create_goal(db, user, a: sc.CreateGoalArgs):
    g = Goal(user_id=user.id, title=a.title, detail=a.detail, horizon=a.horizon,
             category=a.category, target_date=a.target_date)
    db.add(g); db.commit(); db.refresh(g)
    return {"id": str(g.id), "title": g.title, "horizon": g.horizon}


def update_goal(db, user, a: sc.UpdateGoalArgs):
    g = _match(_user_rows(db, user, Goal), a.goal, "title", "category")
    if not g:
        raise ValueError(f"no goal matching “{a.goal}”")
    if a.progress is not None:
        g.progress = max(0, min(100, a.progress))
    if a.status is not None:
        g.status = a.status
    db.commit(); db.refresh(g)
    return goals_svc.detail(db, user, g)


def get_goals(db, user, a: sc.EmptyArgs):
    return goals_svc.listing(db, user)


# ---------------------------------------------------------------- career
def get_career(db, user, a: sc.EmptyArgs):
    apps = _user_rows(db, user, Application)
    interns = {i.id: i for i in _user_rows(db, user, Internship)}
    return [{"company": interns[x.internship_id].company if x.internship_id in interns else "",
             "role": interns[x.internship_id].role if x.internship_id in interns else "",
             "stage": x.stage,
             "deadline": x.deadline.isoformat() if x.deadline else None} for x in apps]


# ---------------------------------------------------------------- read-only rollups
def get_tasks(db, user, a: sc.EmptyArgs):
    rows = db.query(Task).filter(Task.user_id == user.id, Task.status == "open").all()
    return [{"id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None,
             "priority": t.priority} for t in rows]


def get_deadlines(db, user, a: sc.EmptyArgs):
    rows = (db.query(Assignment)
            .filter(Assignment.user_id == user.id, Assignment.status == "open")
            .order_by(Assignment.due_at.asc()).all())
    return [{"id": str(x.id), "title": x.title, "due_at": x.due_at.isoformat()} for x in rows]


def get_progress(db, user, a: sc.EmptyArgs):
    from app.services.progress import snapshot
    return snapshot(db, user)


def get_signals(db, user, a: sc.EmptyArgs):
    spider_sense.scan(db, user)
    return [{"id": str(n.id), "level": n.level, "title": n.title, "module": n.module}
            for n in spider_sense.active(db, user)]


def acknowledge_signal(db, user, a: sc.AcknowledgeSignalArgs):
    n = (db.query(Notification)
         .filter(Notification.id == a.signal_id, Notification.user_id == user.id).first())
    if not n:
        raise ValueError("Signal not found")
    n.acknowledged = True
    db.commit()
    return {"id": str(n.id), "acknowledged": True}


def get_plan_today(db, user, a: sc.EmptyArgs):
    from app.api.routes.planner import _day_payload
    return _day_payload(db, user, 0)


def propose_plan(db, user, a: sc.ProposePlanArgs):
    """Work out a realistic schedule from real deadlines and real free capacity.

    Read-only: it returns a proposal and writes nothing. The orchestrator
    normally intercepts this tool and expands it into concrete intents so the
    user can approve them; reaching the executor directly just returns the plan.
    """
    from app.jocasta import planning
    result = planning.propose(db, user, horizon_days=max(1, min(a.horizon_days, 14)))
    return {"plan": result["plan"], "unplaceable": result["unplaceable"],
            "proposed_changes": len(result["intents"])}


# name -> (arg schema, executor). This registry is the ONLY surface the AI can reach.
REGISTRY = {
    # tasks & reminders
    "create_task": (sc.CreateTaskArgs, create_task),
    "update_task": (sc.UpdateTaskArgs, update_task),
    "complete_task": (sc.TaskIdArgs, complete_task),
    "complete_task_by_name": (sc.CompleteByTitleArgs, complete_task_by_name),
    "reschedule_task": (sc.RescheduleArgs, reschedule_task),
    "find_task": (sc.FindTaskArgs, find_task),
    "create_reminder": (sc.CreateReminderArgs, create_reminder),
    # memory & notes
    "save_memory": (sc.SaveMemoryArgs, save_memory),
    "search_memory": (sc.SearchMemoryArgs, search_memory),
    "update_memory": (sc.UpdateMemoryArgs, update_memory),
    "delete_memory": (sc.MemoryIdArgs, delete_memory),
    "get_memories": (sc.EmptyArgs, get_memories),
    "create_note": (sc.CreateNoteArgs, create_note),
    "search_notes": (sc.SearchNotesArgs, search_notes),
    # college
    "create_assignment": (sc.CreateAssignmentArgs, create_assignment),
    "mark_attendance": (sc.MarkAttendanceArgs, mark_attendance),
    "get_schedule": (sc.EmptyArgs, get_schedule),
    "get_college": (sc.EmptyArgs, get_college),
    # learning
    "log_study": (sc.LogStudyArgs, log_study),
    "schedule_study": (sc.ScheduleStudyArgs, schedule_study),
    "create_topic": (sc.CreateTopicArgs, create_topic),
    "get_learning": (sc.EmptyArgs, get_learning),
    # projects
    "create_project_task": (sc.CreateProjectTaskArgs, create_project_task),
    "get_projects": (sc.EmptyArgs, get_projects),
    # personal
    "log_habit": (sc.LogHabitArgs, log_habit),
    "create_habit": (sc.CreateHabitArgs, create_habit),
    "get_habits": (sc.EmptyArgs, get_habits),
    # finance
    "log_expense": (sc.LogExpenseArgs, log_expense),
    "set_budget": (sc.SetBudgetArgs, set_budget),
    "get_finance": (sc.EmptyArgs, get_finance),
    # goals
    "create_goal": (sc.CreateGoalArgs, create_goal),
    "update_goal": (sc.UpdateGoalArgs, update_goal),
    "get_goals": (sc.EmptyArgs, get_goals),
    # career
    "get_career": (sc.EmptyArgs, get_career),
    # rollups & signals
    "get_tasks": (sc.EmptyArgs, get_tasks),
    "get_deadlines": (sc.EmptyArgs, get_deadlines),
    "get_progress": (sc.EmptyArgs, get_progress),
    "get_signals": (sc.EmptyArgs, get_signals),
    "acknowledge_signal": (sc.AcknowledgeSignalArgs, acknowledge_signal),
    "get_plan_today": (sc.EmptyArgs, get_plan_today),
    "propose_plan": (sc.ProposePlanArgs, propose_plan),
}

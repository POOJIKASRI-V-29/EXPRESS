"""Realistic demo data mirroring the approved EXPRESS design.

`seed` runs once on an empty database. `backfill` runs on every boot of an
already-seeded database and adds *only* entity types that have no rows yet — so
a database created before a module existed gains that module's demo data
without losing anything the user already entered.
"""
from datetime import timedelta
from app.core.config import settings
from app.core.security import hash_password
from app.services.timeutils import now, local_today
from app.services import materialize, spider_sense, habits as habits_svc
from app.models import (
    User, Semester, Course, Class, AcademicEvent, Assignment, Exam, Task, Memory, Note,
    Project, ProjectPhase, ProjectTask, Skill, Internship, Application, LearningTopic,
    LearningSession, Habit, HabitLog, Goal, GoalLink, FinanceEntry, Budget,
)


def at(days, h, m=0):
    return (now() + timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)


def seed(db):
    user = User(email=settings.DEMO_EMAIL, name="Pooji",
                hashed_password=hash_password(settings.DEMO_PASSWORD))
    db.add(user); db.flush()

    sem = Semester(user_id=user.id, label="Semester 5",
                   tagline="Advanced Computer Science & Design Architecture", is_active=True,
                   start_date=at(-60, 9), end_date=at(60, 17))
    db.add(sem); db.flush()

    course_defs = [
        ("ds", "CS301", "Data Structures", "Prof. Alan", "Hall 3A", 92),
        ("os", "CS305", "Operating Systems", "Prof. Rao", "TT 118", 78),
        ("dbms", "CS303", "Database Systems", "Prof. Menon", "Lab B", 88),
        ("uiux", "DS210", "UI/UX Design", "Prof. Iyer", "Studio 1", 65),
        ("ml", "AI310", "Machine Learning", "Prof. Das", "TT 402", 84),
    ]
    courses = {}
    for key, code, name, fac, room, att in course_defs:
        c = Course(user_id=user.id, semester_id=sem.id, code=code, name=name,
                   faculty=fac, room=room, attendance=att)
        db.add(c); db.flush(); courses[key] = c

    # a full week of timetable, not just today
    timetable = [
        (0, "ml", "09:00", "10:30"), (0, "ds", "11:30", "13:00"), (0, "uiux", "14:15", "15:45"),
        (1, "dbms", "09:00", "10:30"), (1, "os", "11:30", "13:00"),
        (2, "ds", "09:00", "10:30"), (2, "ml", "14:15", "15:45"),
        (3, "os", "09:00", "10:30"), (3, "uiux", "11:30", "13:00"),
        (4, "dbms", "09:00", "10:30"), (4, "ds", "11:30", "13:00"),
    ]
    today_dow = now().weekday()
    for dow, key, start, end in timetable:
        db.add(Class(user_id=user.id, course_id=courses[key].id, day_of_week=dow,
                     start_time=start, end_time=end, room=courses[key].room))
    # guarantee today has classes whatever weekday the demo is first run on
    if today_dow > 4:
        for key, start, end in [("ml", "09:00", "10:30"), ("ds", "11:30", "13:00")]:
            db.add(Class(user_id=user.id, course_id=courses[key].id, day_of_week=today_dow,
                         start_time=start, end_time=end, room=courses[key].room))

    # a scheduling conflict today -> Spider Sense critical
    db.add(AcademicEvent(user_id=user.id, semester_id=sem.id, title="Data Science Lab",
                         type="event", date=at(0, 13, 0), end_date=at(0, 15, 0)))
    db.add(AcademicEvent(user_id=user.id, semester_id=sem.id, title="Internship Interview",
                         type="event", date=at(0, 14, 0), end_date=at(0, 14, 45)))
    db.add(AcademicEvent(user_id=user.id, semester_id=sem.id, title="CAT-2 Window",
                         type="exam_window", date=at(5, 9, 0)))
    db.add(AcademicEvent(user_id=user.id, semester_id=sem.id, title="Mid-semester Break",
                         type="break", date=at(21, 0, 0), end_date=at(28, 0, 0)))

    db.add(Exam(user_id=user.id, course_id=courses["dbms"].id, title="DBMS CAT-2",
                type="cat", date=at(6, 10, 0), room="Hall 3A"))
    db.add(Exam(user_id=user.id, course_id=courses["ds"].id, title="DSA CAT-2",
                type="cat", date=at(8, 10, 0), room="Hall 3A"))

    assignment_defs = [
        ("DBMS Assignment", "dbms", "Normalize the schema and implement the query set for the banking module.", at(1, 8, 0), 42, "high"),
        ("UX Research Report", "uiux", "Finalize user personas and journey maps for the mobile banking app.", at(0, 23, 59), 90, "high"),
        ("Binary Tree Implementation", "ds", "Complete the C++ implementation of AVL tree balancing algorithms.", at(3, 23, 59), 120, "med"),
        ("Model Training Essay", "ml", "Compare optimizers and write up the training methodology.", at(6, 23, 59), 60, "low"),
    ]
    for title, ck, desc, due, est, pr in assignment_defs:
        a = Assignment(user_id=user.id, course_id=courses[ck].id, title=title, description=desc,
                       due_at=due, est_minutes=est, priority=pr)
        db.add(a); db.flush()
        materialize.task_for_assignment(db, a)   # Assignment -> Task

    # standalone personal tasks (Up Next)
    db.add(Task(user_id=user.id, title="Evening Workout", category="Routine", due_at=at(0, 18, 30),
                est_minutes=45, icon="dumb", meta="Upper Body Strength"))
    db.add(Task(user_id=user.id, title="Inbox Zero", category="Routine", due_at=at(0, 19, 45),
                est_minutes=20, icon="mail", meta="12 unread"))
    db.add(Task(user_id=user.id, title="Revise Trees (DSA)", category="Learning", due_at=at(0, 21, 0),
                est_minutes=30, icon="learning", meta="Postponed twice", postpone_count=2))  # -> Spider Sense

    for text_, cat in [("I prefer studying DSA at night.", "Preference"),
                       ("Project teammates: Aditi, Rohan, Sneha.", "Person")]:
        db.add(Memory(user_id=user.id, text=text_, category=cat, source="manual"))

    proj = Project(user_id=user.id, name="EXPRESS OS",
                   description="A comprehensive personal operating system interface simulating a high-end desktop environment.",
                   phase="Backend Core", commits=142, stack="Tailwind/JS", status="Active",
                   completion=50, priority=1, due_at=at(30, 18, 0),
                   repo_url="https://github.com/example/express-os")
    db.add(proj); db.flush()
    for i, (name, done) in enumerate([("Foundations", True), ("Design System", True),
                                      ("Backend Core", False), ("Integrations", False)]):
        db.add(ProjectPhase(project_id=proj.id, name=name, order=i, done=done))
    for title, due in [("Wire the Planner timeline", at(2, 20, 0)),
                       ("Write the Memory module UI", at(4, 20, 0))]:
        pt = ProjectTask(user_id=user.id, project_id=proj.id, title=title, due_at=due)
        db.add(pt); db.flush()
        materialize.task_for_project_task(db, pt)

    portfolio = Project(user_id=user.id, name="Portfolio Site",
                        description="Personal site with case studies and a writing section.",
                        phase="Design System", commits=38, stack="Next.js", status="Active",
                        completion=0, priority=2)
    db.add(portfolio); db.flush()
    for i, (name, done) in enumerate([("Content", True), ("Design System", False), ("Ship", False)]):
        db.add(ProjectPhase(project_id=portfolio.id, name=name, order=i, done=done))
    portfolio.completion = 33

    intern_defs = [("Stark Industries", "Software Engineering Intern", "Interviewing", "interview", at(2, 11, 0)),
                   ("Google", "Data Analyst", "Applied", "applied", None)]
    for comp, role, status, stage, deadline in intern_defs:
        it = Internship(user_id=user.id, company=comp, role=role, status=status, location="Remote")
        db.add(it); db.flush()
        ap = Application(user_id=user.id, internship_id=it.id, stage=stage, deadline=deadline,
                         notes="Prep system design + DSA." if stage == "interview" else "")
        db.add(ap); db.flush()
        materialize.task_for_application(db, ap, it)

    for name, lvl, pct in [("Python / Backend", 4, 80), ("AI / ML Fundamentals", 2, 40),
                           ("Data Structures (DSA)", 3, 62)]:
        db.add(Skill(user_id=user.id, name=name, level=lvl, pct=pct))

    topic_rows = {}
    for name, area, state, prog, ck in [("Trees & Graphs", "DSA", "needs_revision", 55, "ds"),
                                        ("Transformers", "AI/ML", "learning", 30, "ml"),
                                        ("Pandas", "DataScience", "strong", 90, None),
                                        ("Normalization", "Course", "practicing", 60, "dbms")]:
        t = LearningTopic(user_id=user.id, name=name, area=area, state=state, progress=prog,
                          course_id=courses[ck].id if ck else None)
        db.add(t); db.flush(); topic_rows[name] = t

    for name, days_ago, mins in [("Pandas", 1, 45), ("Transformers", 2, 60), ("Pandas", 4, 30),
                                 ("Normalization", 3, 40), ("Transformers", 6, 25)]:
        t = topic_rows[name]
        started = at(-days_ago, 20, 0)
        db.add(LearningSession(user_id=user.id, topic_id=t.id, minutes=mins, started_at=started))
        if t.last_reviewed_at is None or started > t.last_reviewed_at:
            t.last_reviewed_at = started

    db.commit()
    backfill(db, user)               # habits, goals, notes, finance
    spider_sense.scan(db, user)      # generate initial notifications
    print(f"[seed] demo user: {settings.DEMO_EMAIL} / {settings.DEMO_PASSWORD}")


def _has(db, model, user) -> bool:
    return db.query(model).filter(model.user_id == user.id).count() > 0


def backfill(db, user=None):
    """Add demo rows only for entity types that are still empty. Idempotent:
    running it on a fully-populated database changes nothing."""
    if user is None:
        user = db.query(User).filter(User.email == settings.DEMO_EMAIL).first()
    if not user:
        return
    added = []

    if not _has(db, Habit, user):
        today = local_today()
        habit_defs = [("Morning workout", "dumb", 5, [1, 2, 3, 5]),
                      ("Read 20 pages", "learning", 7, [0, 1, 2, 3, 4]),
                      ("No phone after 11pm", "check", 7, [0, 2, 3])]
        for title, icon, target, offsets in habit_defs:
            h = Habit(user_id=user.id, title=title, icon=icon, target_per_week=target)
            db.add(h); db.flush()
            for off in offsets:
                db.add(HabitLog(user_id=user.id, habit_id=h.id, on_date=today - timedelta(days=off)))
            db.flush()
            habits_svc.recompute(db, user, h)
        added.append("habits")

    if not _has(db, Goal, user):
        proj = db.query(Project).filter(Project.user_id == user.id).first()
        topic = db.query(LearningTopic).filter(LearningTopic.user_id == user.id,
                                               LearningTopic.name == "Trees & Graphs").first()
        skill = db.query(Skill).filter(Skill.user_id == user.id).first()
        g1 = Goal(user_id=user.id, title="Ship EXPRESS OS v1", horizon="short", category="projects",
                  detail="Every module real, connected and deployed.", target_date=at(30, 18, 0))
        g2 = Goal(user_id=user.id, title="Crack DSA interviews", horizon="long", category="career",
                  detail="Strong on trees, graphs and DP before placement season.",
                  target_date=at(90, 9, 0))
        db.add_all([g1, g2]); db.flush()
        if proj:
            db.add(GoalLink(user_id=user.id, goal_id=g1.id, ref_type="project", ref_id=proj.id))
        if topic:
            db.add(GoalLink(user_id=user.id, goal_id=g2.id, ref_type="topic", ref_id=topic.id))
        if skill:
            db.add(GoalLink(user_id=user.id, goal_id=g2.id, ref_type="skill", ref_id=skill.id))
        added.append("goals")

    if not _has(db, Exam, user):
        courses = {c.name: c for c in db.query(Course).filter(Course.user_id == user.id).all()}
        for title, cname, days, room in [("DBMS CAT-2", "Database Systems", 6, "Hall 3A"),
                                         ("DSA CAT-2", "Data Structures", 8, "Hall 3A")]:
            c = courses.get(cname)
            db.add(Exam(user_id=user.id, course_id=c.id if c else None, title=title,
                        type="cat", date=at(days, 10, 0), room=room))
        added.append("exams")

    if not _has(db, LearningSession, user):
        topics = {t.name: t for t in db.query(LearningTopic)
                  .filter(LearningTopic.user_id == user.id).all()}
        for name, days_ago, mins in [("Pandas", 1, 45), ("Transformers", 2, 60), ("Pandas", 4, 30),
                                     ("Trees & Graphs", 3, 40), ("Transformers", 6, 25)]:
            t = topics.get(name)
            if not t:
                continue
            started = at(-days_ago, 20, 0)
            db.add(LearningSession(user_id=user.id, topic_id=t.id, minutes=mins, started_at=started))
            if t.last_reviewed_at is None or started > t.last_reviewed_at:
                t.last_reviewed_at = started
        added.append("learning sessions")

    if not _has(db, Note, user):
        proj = db.query(Project).filter(Project.user_id == user.id).first()
        db.add(Note(user_id=user.id, title="Interview prep plan",
                    body="System design: caching, rate limiting, sharding. DSA: trees, graphs, DP. "
                         "One mock a week with Rohan.",
                    tags="career,dsa", pinned=True))
        db.add(Note(user_id=user.id, title="Architecture decisions",
                    body="Every module writes through the Task queue so Planner needs no special "
                         "cases. Spider Sense reads the same services the pages read.",
                    tags="express,architecture",
                    ref_type="project" if proj else "", ref_id=proj.id if proj else None))
        added.append("notes")

    if not _has(db, FinanceEntry, user):
        entries = [(320, "Food", "expense", "Canteen top-up", 1), (1200, "Books", "expense", "DS textbook", 3),
                   (150, "Transport", "expense", "Metro card", 2), (480, "Food", "expense", "Weekend groceries", 5),
                   (99, "Subscriptions", "expense", "Music", 6), (5000, "Income", "income", "Freelance payout", 8),
                   (260, "Food", "expense", "Coffee runs", 0)]
        for amount, cat, kind, note_, days_ago in entries:
            db.add(FinanceEntry(user_id=user.id, amount=amount, category=cat, kind=kind,
                                note=note_, date=at(-days_ago, 13, 0)))
        for cat, limit in [("Food", 2000), ("Books", 1500), ("Transport", 800), ("Subscriptions", 500)]:
            db.add(Budget(user_id=user.id, category=cat, monthly_limit=limit))
        added.append("finance")

    if added:
        db.commit()
        spider_sense.scan(db, user)
        print(f"[seed] backfilled: {', '.join(added)}")

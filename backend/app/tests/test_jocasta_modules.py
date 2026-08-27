"""JOCasta reaching every module through the rule planner (no API key needed)."""
from datetime import timedelta
from app.models import (User, Task, Note, Goal, FinanceEntry, Budget, Habit, HabitLog,
                        LearningTopic, LearningSession, Course, Project, ProjectTask, Assignment)
from app.core.security import hash_password
from app.services.timeutils import now, local_today, as_utc
from app.jocasta import orchestrator


def _user(db, email="m@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _call(out, tool):
    return next((c for c in out["calls"] if c["tool"] == tool), None)


def test_questions_never_write(db_session):
    u = _user(db_session)
    before = db_session.query(Task).filter(Task.user_id == u.id).count()
    for q in ["what's due?", "how am i doing", "my schedule", "what are my goals",
              "my habits", "how much have i spent", "anything urgent", "my projects"]:
        out = orchestrator.run(db_session, u, q)
        assert all(c["tool"].startswith("get_") for c in out["calls"]), q
    assert db_session.query(Task).filter(Task.user_id == u.id).count() == before


def test_log_expense_reports_budget_pressure(db_session):
    u = _user(db_session)
    db_session.add(Budget(user_id=u.id, category="Food", monthly_limit=1000))
    db_session.commit()
    out = orchestrator.run(db_session, u, "spent 900 on food today")
    call = _call(out, "log_expense")
    assert call and call["ok"]
    assert call["result"]["budget"]["pct"] == 90
    assert "90% of your Food budget" in out["reply"]
    assert db_session.query(FinanceEntry).filter(FinanceEntry.user_id == u.id).count() == 1


def test_log_study_matches_topic_by_name(db_session):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Trees & Graphs", area="DSA", progress=10))
    db_session.commit()
    out = orchestrator.run(db_session, u, "studied trees for 60 minutes")
    call = _call(out, "log_study")
    assert call and call["ok"] and call["result"]["topic"] == "Trees & Graphs"
    assert call["result"]["progress"] > 10
    assert db_session.query(LearningSession).filter(LearningSession.user_id == u.id).count() == 1


def test_schedule_study_lands_on_the_planner(db_session):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Transformers", area="AI/ML"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "revise transformers tomorrow at 9pm")
    call = _call(out, "schedule_study")
    assert call and call["ok"]
    t = db_session.query(Task).filter(Task.user_id == u.id, Task.source == "learning").one()
    assert "Transformers" in t.title


def test_mark_attendance_by_course_name(db_session):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Operating Systems", code="CS305", attendance=80))
    db_session.commit()
    out = orchestrator.run(db_session, u, "missed operating systems")
    call = _call(out, "mark_attendance")
    assert call and call["ok"] and call["result"]["attended"] is False
    assert call["result"]["attendance"] < 80


def test_complete_task_by_name(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Wash shoes"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "finished washing shoes")
    call = _call(out, "complete_task_by_name")
    assert call and call["ok"]
    assert db_session.query(Task).filter(Task.user_id == u.id).one().status == "done"


def test_unmatched_name_fails_loudly_instead_of_guessing(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Wash shoes"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "finished the quantum thermodynamics report")
    call = _call(out, "complete_task_by_name")
    assert call and not call["ok"]
    assert db_session.query(Task).filter(Task.user_id == u.id).one().status == "open"
    assert "couldn't" in out["reply"]


def test_log_habit_advances_the_streak(db_session):
    u = _user(db_session)
    h = Habit(user_id=u.id, title="Morning workout")
    db_session.add(h); db_session.flush()
    db_session.add(HabitLog(user_id=u.id, habit_id=h.id, on_date=local_today() - timedelta(days=1)))
    db_session.commit()
    out = orchestrator.run(db_session, u, "did my morning workout today")
    call = _call(out, "log_habit")
    assert call and call["ok"] and call["result"]["streak"] == 2


def test_create_goal_and_note(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "my goal is to crack DSA interviews")
    assert _call(out, "create_goal")["ok"]
    assert db_session.query(Goal).filter(Goal.user_id == u.id).count() == 1

    out = orchestrator.run(db_session, u, "make a note that the mock interview is with Rohan")
    assert _call(out, "create_note")["ok"]
    assert db_session.query(Note).filter(Note.user_id == u.id).count() == 1


def test_create_assignment_attaches_to_a_course_and_materializes(db_session):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Database Systems", code="CS303"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "add assignment normalization worksheet for database systems tomorrow")
    call = _call(out, "create_assignment")
    assert call and call["ok"] and call["result"]["course"] == "Database Systems"
    assert db_session.query(Assignment).filter(Assignment.user_id == u.id).count() == 1
    assert db_session.query(Task).filter(Task.user_id == u.id, Task.source == "assignment").count() == 1


def test_project_task_by_project_name(db_session):
    u = _user(db_session)
    db_session.add(Project(user_id=u.id, name="Portfolio Site"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "add write the case study to the portfolio site project")
    call = _call(out, "create_project_task")
    assert call and call["ok"] and call["result"]["project"] == "Portfolio Site"
    assert db_session.query(ProjectTask).filter(ProjectTask.user_id == u.id).count() == 1


def test_reply_reports_the_modules_it_touched(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "remember that I prefer DSA at night")
    assert out["modules"] == ["memory"]
    assert out["reply"] == "Saved to memory."


def test_memory_saved_by_jocasta_is_attributed(db_session):
    from app.models import Memory
    u = _user(db_session)
    orchestrator.run(db_session, u, "remember that I prefer DSA at night")
    m = db_session.query(Memory).filter(Memory.user_id == u.id).one()
    assert m.source == "jocasta" and m.category == "Preference"


def test_name_matching_cannot_cross_users(db_session):
    u1 = _user(db_session, "a@express.os")
    u2 = _user(db_session, "b@express.os")
    db_session.add(LearningTopic(user_id=u1.id, name="Trees & Graphs", area="DSA"))
    db_session.commit()
    out = orchestrator.run(db_session, u2, "studied trees for 30 minutes")
    call = _call(out, "log_study")
    assert call and not call["ok"]           # u2 has no such topic — no silent cross-user match
    assert db_session.query(LearningSession).count() == 0


def test_relative_dates_resolve_forward(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "remind me to submit the form tomorrow at 8am")
    call = _call(out, "create_reminder")
    assert call and call["ok"]
    remind_at = call["result"]["remind_at"]
    from datetime import datetime
    # SQLite hands back naive datetimes where Postgres returns aware ones.
    assert as_utc(datetime.fromisoformat(remind_at)) > now()
    assert "form" in call["result"]["title"].lower()

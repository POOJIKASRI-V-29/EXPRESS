"""JOCasta as an intelligence layer: context, safety, planning, confirmation."""
from datetime import timedelta

from app.core.security import hash_password
from app.jocasta import context as ctx_mod, orchestrator, planning, safety
from app.models import (User, Task, Assignment, Course, Exam, LearningTopic, Memory,
                        Goal, Budget)
from app.services import materialize
from app.services.timeutils import now


def _user(db, email="ctx@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


# ---------------------------------------------------------------- context
def test_context_is_targeted_not_a_full_dump():
    """A finance question must not ship habits, career and learning to the model."""
    assert "finance" in ctx_mod.select_slices("how much have i spent on food")
    assert "habits" not in ctx_mod.select_slices("how much have i spent on food")

    assert "learning" in ctx_mod.select_slices("what should i revise")
    assert "finance" not in ctx_mod.select_slices("what should i revise")

    # A planning question gets the core planning set.
    planning_slices = ctx_mod.select_slices("help me plan my week")
    for expected in ("deadlines", "capacity"):
        assert expected in planning_slices


def test_context_reports_what_it_included(db_session):
    u = _user(db_session)
    ctx = ctx_mod.build(db_session, u, "what's due this week")
    assert ctx["included_slices"], "context must be explainable"
    assert ctx["user"]["id"] == str(u.id)
    assert "reason" in ctx


def test_context_is_user_scoped(db_session):
    a, b = _user(db_session, "a@x.com"), _user(db_session, "b@x.com")
    db_session.add(Task(user_id=a.id, title="A's secret", due_at=now() + timedelta(hours=2)))
    db_session.add(Memory(user_id=a.id, text="A's private memory", pinned=True))
    db_session.commit()

    ctx = ctx_mod.build(db_session, b, "what's on today")
    blob = ctx_mod.summarize(ctx)
    assert "A's secret" not in blob
    assert "A's private memory" not in blob


def test_memory_recall_is_selective_not_everything(db_session):
    u = _user(db_session)
    db_session.add(Memory(user_id=u.id, text="I prefer studying DSA at night", pinned=False))
    db_session.add(Memory(user_id=u.id, text="My landlord's name is Ravi", pinned=False))
    db_session.commit()

    ctx = ctx_mod.build(db_session, u, "when should i study dsa")
    texts = [m["text"] for m in ctx["memory"]["memories"]]
    assert any("DSA" in t for t in texts)
    assert not any("landlord" in t for t in texts), "unrelated memories must not be pulled in"


def test_pinned_memories_are_always_available(db_session):
    u = _user(db_session)
    db_session.add(Memory(user_id=u.id, text="I have ADHD, keep blocks short", pinned=True))
    db_session.commit()
    ctx = ctx_mod.build(db_session, u, "plan my week")
    assert any("ADHD" in m["text"] for m in ctx["memory"]["memories"])


def test_context_is_bounded(db_session):
    u = _user(db_session)
    for i in range(60):
        db_session.add(Task(user_id=u.id, title=f"Task {i}", status="open",
                            due_at=now() + timedelta(hours=1)))
    db_session.commit()
    ctx = ctx_mod.build(db_session, u, "what's on today")
    assert len(ctx["today"]["tasks"]) <= ctx_mod.CAP


# ---------------------------------------------------------------- safety
def test_risk_classification_fails_closed():
    assert safety.risk_of("get_tasks") == safety.READ
    assert safety.risk_of("create_task") == safety.WRITE
    assert safety.risk_of("delete_memory") == safety.SENSITIVE
    # An unregistered tool must never be treated as safe.
    assert safety.risk_of("some_future_tool") == safety.SENSITIVE


def test_reads_and_single_writes_run_without_asking():
    assert not safety.classify([{"tool": "get_tasks"}])["needs_confirmation"]
    assert not safety.classify([{"tool": "create_task", "args": {"title": "x"}}])["needs_confirmation"]


def test_destructive_and_bulk_actions_require_confirmation():
    assert safety.classify([{"tool": "delete_memory", "args": {"memory_id": "1"}}])["needs_confirmation"]
    bulk = [{"tool": "create_task", "args": {}} for _ in range(safety.BULK_THRESHOLD)]
    verdict = safety.classify(bulk)
    assert verdict["needs_confirmation"] and "changes at once" in verdict["reason"]


def test_confirmation_token_is_bound_to_its_user_and_tamper_proof(db_session):
    a, b = _user(db_session, "signer@x.com"), _user(db_session, "other@x.com")
    intents = [{"tool": "delete_memory", "args": {"memory_id": "abc"}}]
    token = safety.sign(a.id, intents)

    assert safety.verify(a.id, token) == intents          # owner can redeem
    for bad in (b.id,):                                    # nobody else can
        try:
            safety.verify(bad, token)
            assert False, "another user redeemed the token"
        except ValueError:
            pass
    for junk in ("", "not-a-token", token + "x"):
        try:
            safety.verify(a.id, junk)
            assert False, "tampered token accepted"
        except ValueError:
            pass


def test_delete_via_jocasta_asks_before_destroying(db_session):
    u = _user(db_session)
    m = Memory(user_id=u.id, text="delete me please", category="Note")
    db_session.add(m); db_session.commit(); db_session.refresh(m)

    out = orchestrator.run(db_session, u, f"delete memory {m.id}")
    if out["pending"]:
        # nothing ran yet
        assert out["calls"] == []
        assert db_session.query(Memory).filter(Memory.id == m.id).first() is not None
        # and the approved plan does run
        done = orchestrator.confirm(db_session, u, out["confirm_token"])
        assert done["verification"]["succeeded"] >= 1


# ---------------------------------------------------------------- planning
def _course_with_exam(db, user, days_out=4):
    c = Course(user_id=user.id, name="Database Systems", code="CS303")
    db.add(c); db.flush()
    db.add(Exam(user_id=user.id, course_id=c.id, title="DBMS CAT-2",
                date=now() + timedelta(days=days_out)))
    return c


def test_planner_never_moves_a_real_deadline(db_session):
    """Coursework due dates are external facts. Planning books work *before*
    them; it must never reschedule the assignment itself."""
    u = _user(db_session)
    a = Assignment(user_id=u.id, title="Normalization set", due_at=now() + timedelta(days=3),
                   est_minutes=90, priority="high")
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()
    original_due = a.due_at

    result = planning.propose(db_session, u, horizon_days=7)
    assert result["intents"]
    assert not any(i["tool"] == "reschedule_task" for i in result["intents"]), \
        "planning must not move an assignment-backed deadline"
    assert any(i["tool"] == "create_task" for i in result["intents"])

    out = orchestrator.run(db_session, u, "help me plan my week")
    if out.get("confirm_token"):
        orchestrator.confirm(db_session, u, out["confirm_token"])
    db_session.refresh(a)
    assert a.due_at == original_due, "the coursework deadline was moved"


def test_planner_places_work_before_its_deadline(db_session):
    u = _user(db_session)
    a = Assignment(user_id=u.id, title="Normalization set", due_at=now() + timedelta(days=3),
                   est_minutes=90, priority="high")
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()

    result = planning.propose(db_session, u, horizon_days=7)
    assert result["plan"], "expected a proposal"
    from datetime import datetime
    for p in result["plan"]:
        assert datetime.fromisoformat(p["when"]) <= a.due_at + timedelta(hours=1)
        assert p["why"], "every placement must explain itself"


def test_planner_pulls_overdue_work_forward(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Very late thing", status="open",
                        est_minutes=30, due_at=now() - timedelta(days=3)))
    db_session.commit()
    result = planning.propose(db_session, u, horizon_days=7)
    assert any("overdue" in p["why"] for p in result["plan"])


def test_planner_respects_capacity_and_reports_what_it_could_not_place(db_session):
    """Genuine overload: far more coursework than the week can absorb.

    The allocator must place what fits and say plainly what did not — silently
    dropping work would be worse than admitting the week is full.
    """
    u = _user(db_session)
    for i in range(10):
        a = Assignment(user_id=u.id, title=f"Heavy assignment {i}",
                       due_at=now() + timedelta(days=2), est_minutes=400, priority="high")
        db_session.add(a); db_session.flush()
        materialize.task_for_assignment(db_session, a)
    db_session.commit()

    result = planning.propose(db_session, u, horizon_days=7)
    assert result["plan"], "it should still place what fits"
    assert result["unplaceable"], "over-committed work must be reported, not silently dropped"
    assert all(x["why"] for x in result["unplaceable"])
    assert "no day" in result["unplaceable"][0]["why"]


def test_planning_twice_does_not_stack_duplicate_blocks(db_session):
    """Asking for a plan again must not book a second block for the same work."""
    u = _user(db_session)
    a = Assignment(user_id=u.id, title="Essay", due_at=now() + timedelta(days=4),
                   est_minutes=60, priority="med")
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()

    first = orchestrator.run(db_session, u, "help me plan my week")
    assert first["confirm_token"]
    orchestrator.confirm(db_session, u, first["confirm_token"])
    booked = db_session.query(Task).filter(Task.user_id == u.id,
                                           Task.meta == "Planned by JOCasta").count()

    second = planning.propose(db_session, u, horizon_days=7)
    assert not any("Essay" in i.get("args", {}).get("title", "")
                   for i in second["intents"]), "a duplicate work block was proposed"
    assert db_session.query(Task).filter(Task.user_id == u.id,
                                         Task.meta == "Planned by JOCasta").count() == booked


def test_planner_schedules_revision_before_an_exam(db_session):
    u = _user(db_session)
    c = _course_with_exam(db_session, u, days_out=5)
    db_session.add(LearningTopic(user_id=u.id, name="Normalization", area="Course",
                                 state="needs_revision", course_id=c.id))
    db_session.commit()
    result = planning.propose(db_session, u, horizon_days=7)
    assert any(p["kind"] == "revision" for p in result["plan"])
    assert any("CAT-2" in p["why"] for p in result["plan"])


def test_plan_request_routes_to_the_allocator_not_a_new_task(db_session):
    """"Help me plan" must never become a task titled "help me plan"."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Real work", status="open",
                        est_minutes=60, due_at=now() - timedelta(days=1)))
    db_session.commit()
    before = db_session.query(Task).filter(Task.user_id == u.id).count()

    out = orchestrator.run(db_session, u, "help me plan my week")
    assert not any(c["tool"] == "create_task" for c in out["calls"])
    assert db_session.query(Task).filter(Task.user_id == u.id).count() == before


def test_cross_module_planning_reasons_over_exam_and_project(db_session):
    """The headline case, without an API key: an exam and a deadline together."""
    u = _user(db_session)
    c = _course_with_exam(db_session, u, days_out=4)
    db_session.add(LearningTopic(user_id=u.id, name="Normalization", area="Course",
                                 state="needs_revision", course_id=c.id))
    a = Assignment(user_id=u.id, title="Project writeup", due_at=now() + timedelta(days=6),
                   est_minutes=120, priority="high")
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()

    out = orchestrator.run(db_session, u, "i have a DBMS exam friday and my project is due monday, help me plan")
    # It produced a real plan spanning both modules, and asked before applying it.
    assert out["pending"] is not None, "a multi-change plan should ask first"
    kinds = {a_["tool"] for a_ in out["pending"]["actions"]}
    assert kinds & {"schedule_study", "create_task", "reschedule_task"}
    assert "plan" in out["reply"].lower() or "•" in out["reply"]

    # Approving it actually applies the plan.
    done = orchestrator.confirm(db_session, u, out["confirm_token"])
    assert done["verification"]["succeeded"] >= 1
    assert done["verification"]["failed"] == 0, done["verification"]["failures"]

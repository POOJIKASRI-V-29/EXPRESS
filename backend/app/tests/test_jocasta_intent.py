"""Intent classification, and the guarantee that talking never writes.

The bug these exist to prevent: the planner used to fall through to
`create_task` for anything it didn't recognise, so ordinary conversation
silently created records.
"""
import pytest

from app.core.security import hash_password
from app.jocasta import orchestrator
from app.jocasta.intent import Intent, classify, may_write
from app.models import Course, CourseModule, CourseTopic, Memory, Task, User
from app.services import courses as course_svc


def _user(db, email="int@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _tasks(db, user):
    return db.query(Task).filter(Task.user_id == user.id).count()


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("text", [
    "hey jocasta", "hi", "hello there", "good morning",
    "how are you", "how's it going", "who are you", "what can you do",
    "thanks", "thank you", "ok", "ok cool", "yeah thanks", "never mind",
    "i'm tired", "i am exhausted", "feeling stressed",
])
def test_conversation_is_recognised(text):
    intent, _ = classify(text)
    assert intent is Intent.CONVERSATION, f"{text!r} -> {intent}"
    assert not may_write(intent)


@pytest.mark.parametrize("text,expected", [
    ("what should i do right now", Intent.SUGGESTION),
    ("what should i study tonight", Intent.SUGGESTION),
    ("i have two hours free tonight", Intent.SUGGESTION),
    ("plan my day", Intent.PLANNING),
    ("help me plan my week", Intent.PLANNING),
    ("what do i have today", Intent.READ),
    ("what's on my schedule tomorrow", Intent.READ),
    ("what am i behind on", Intent.READ),
    ("how is my dbms going", Intent.READ),
    ("add dsa practice tomorrow at 7", Intent.CREATE),
    ("revise transformers tomorrow at 9pm", Intent.CREATE),
    ("move it to 8", Intent.RESCHEDULE),
    ("push my study session to friday", Intent.RESCHEDULE),
    ("delete the dsa task", Intent.DELETE),
    ("cancel my 7pm study session", Intent.DELETE),
    ("i finished binary trees", Intent.COMPLETE),
    ("i attended dbms today", Intent.ATTENDANCE),
    ("i missed ml today", Intent.ATTENDANCE),
    ("remember that i study dsa in the evening", Intent.MEMORY),
    ("spent 320 on food today", Intent.LOG),
    ("studied trees for 45 minutes", Intent.LOG),
])
def test_intents_are_classified(text, expected):
    intent, why = classify(text)
    assert intent is expected, f"{text!r} -> {intent.value} ({why})"


@pytest.mark.parametrize("text", [
    "schedule something for tonight", "add it", "delete that", "move that",
    "do something", "create",
])
def test_vague_instructions_ask_rather_than_act(text):
    intent, _ = classify(text)
    assert intent in (Intent.CLARIFY, Intent.RESCHEDULE, Intent.DELETE), text


def test_an_unrecognised_statement_is_not_a_create():
    """The whole point: silence is not consent to file a record."""
    for text in ("the weather is nice", "my flatmate is loud", "hmm"):
        intent, _ = classify(text)
        assert intent is not Intent.CREATE, text
        assert not may_write(intent), text


# ---------------------------------------------------------------- no writes
@pytest.mark.parametrize("text", [
    "hey jocasta", "how are you", "i'm tired", "thanks", "ok cool",
    "what should i do right now", "i have two hours free tonight",
    "what do i have today", "the weather is nice", "hmm",
])
def test_conversation_never_creates_a_record(db_session, text):
    u = _user(db_session)
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, text)
    assert _tasks(db_session, u) == before, f"{text!r} created a task"
    assert not any(c["tool"] == "create_task" for c in out["calls"]), out["calls"]
    assert out["reply"], "a conversational turn still owes the user an answer"


def test_greeting_gets_a_real_reply_not_a_confirmation(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "hey jocasta")
    assert out["intent"] == "conversation"
    assert out["calls"] == []
    assert "add" not in out["reply"].lower()


def test_suggestion_reads_but_does_not_write(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Real work", status="open"))
    db_session.commit()
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, "what should i do right now")
    assert _tasks(db_session, u) == before
    assert out["intent"] == "suggestion"


def test_stated_free_time_is_advice_not_a_booking(db_session):
    u = _user(db_session)
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, "i have two hours free tonight")
    assert _tasks(db_session, u) == before
    assert out["calls"] == []
    assert out["reply"]


def test_a_read_intent_cannot_reach_a_mutating_tool(db_session):
    """Even if a planner proposed one, the guard drops it."""
    u = _user(db_session)
    before = _tasks(db_session, u)
    for text in ("what's on my schedule", "what am i behind on", "show me my tasks"):
        out = orchestrator.run(db_session, u, text)
        assert all(not c["tool"].startswith(("create_", "delete_", "reschedule_"))
                   for c in out["calls"]), (text, out["calls"])
    assert _tasks(db_session, u) == before


# ---------------------------------------------------------------- writes still work
def test_explicit_instructions_still_write(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "add dsa practice tomorrow at 7pm")
    assert any(c["tool"] == "create_task" and c["ok"] for c in out["calls"]), out["calls"]
    assert _tasks(db_session, u) == 1


def test_memory_instruction_still_writes(db_session):
    u = _user(db_session)
    orchestrator.run(db_session, u, "remember that i study dsa in the evening")
    assert db_session.query(Memory).filter(Memory.user_id == u.id).count() == 1


# ---------------------------------------------------------------- follow-ups
def test_a_follow_up_with_no_subject_asks(db_session):
    """"Move it" with nothing recent must not act on a guess."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Something", status="open"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "move it to 8")
    assert out["calls"] == []
    assert "which one" in out["reply"].lower() or "not sure" in out["reply"].lower()


def test_a_follow_up_resolves_against_what_was_just_created(db_session):
    u = _user(db_session)
    made = orchestrator.run(db_session, u, "add dsa practice tomorrow at 7pm")
    assert any(c["ok"] for c in made["calls"])

    out = orchestrator.run(db_session, u, "move it to 8pm")
    # Either it rescheduled the right task, or it asked — never a second task.
    assert not any(c["tool"] == "create_task" for c in out["calls"])
    assert _tasks(db_session, u) == 1, "a follow-up created a duplicate"


# ---------------------------------------------------------------- ambiguity
def test_an_ambiguous_delete_asks_instead_of_deleting(db_session):
    u = _user(db_session)
    for title in ("DSA practice", "DSA revision"):
        db_session.add(Task(user_id=u.id, title=title, status="open"))
    db_session.commit()

    out = orchestrator.run(db_session, u, "delete the dsa task")
    call = next((c for c in out["calls"] if c["tool"] == "delete_task"), None)
    if call:
        assert not call["ok"], "deleted one of two equally plausible matches"
        assert "which" in (call["error"] or "").lower()
    assert _tasks(db_session, u) == 2, "an ambiguous delete removed something"


def test_an_unambiguous_delete_works(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Dentist appointment", status="open"))
    db_session.commit()
    out = orchestrator.run(db_session, u, "delete the dentist appointment")
    assert out.get("pending") or any(c["ok"] for c in out["calls"])
    if out.get("confirm_token"):
        orchestrator.confirm(db_session, u, out["confirm_token"])
    assert _tasks(db_session, u) == 0

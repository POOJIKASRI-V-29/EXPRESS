"""Behaviour fixes found by hand-testing JOCasta.

Each test here corresponds to something that was actually wrong: ordinary
conversation being answered with "I'm not sure what to do with that",
suggestions built on junk rows, a study session described as a deadline, and
internal tool names leaking into replies.
"""
from datetime import timedelta

import pytest

from app.core.security import hash_password
from app.jocasta import conversation, orchestrator, safety
from app.jocasta.intent import Intent, classify
from app.jocasta.orchestrator import TOOL_MODULE, _one
from app.jocasta.tools import REGISTRY
from app.models import (Assignment, Course, CourseModule, CourseTopic, Goal,
                        LearningTopic, Task, User)
from app.services import materialize
from app.services.timeutils import now


def _user(db, email="beh@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _tasks(db, user):
    return db.query(Task).filter(Task.user_id == user.id).count()


# ---------------------------------------------------------------- 1. conversation
@pytest.mark.parametrize("text", [
    "Hey Jocasta, how are you?", "Hey, how are you?", "hey jocasta",
    "How are you?", "hi there how are you", "Good morning", "Good night",
    "Thanks", "Thanks!", "I'm tired", "I'm bored", "Okay", "Cool", "Nice",
    "you ok?", "hello how are you doing",
])
def test_ordinary_conversation_is_recognised(text):
    intent, why = classify(text)
    assert intent is Intent.CONVERSATION, f"{text!r} -> {intent.value} ({why})"


@pytest.mark.parametrize("text", [
    "Hey Jocasta, how are you?", "I'm tired.", "Thanks.", "Good night", "Cool",
])
def test_conversation_answers_and_never_writes(db_session, text):
    u = _user(db_session)
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, text)

    assert out["calls"] == [], f"{text!r} called tools: {out['calls']}"
    assert _tasks(db_session, u) == before, f"{text!r} created a record"
    assert out["reply"], "conversation still owes an answer"
    # The exact failure the user reported.
    assert "not sure what to do with that" not in out["reply"].lower()


@pytest.mark.parametrize("text", ["bye", "goodbye", "good night", "see you", "night", "later"])
def test_sign_offs_are_conversation(text):
    assert classify(text)[0] is Intent.CONVERSATION, text


def test_a_sign_off_does_not_list_outstanding_work(db_session):
    """Ending the day is the wrong moment to be handed a to-do list."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Overdue thing", status="open",
                        due_at=now() - timedelta(days=2)))
    db_session.commit()
    reply = conversation.conversation_reply(db_session, u, "good night")
    assert "overdue thing" not in reply.lower()
    assert "night" in reply.lower()


def test_an_overdue_item_is_never_described_as_due_in_negative_hours(db_session):
    """`hours_until` goes negative once something is late; formatting it raw
    produced "it's due in about -66h"."""
    u = _user(db_session)
    a = Assignment(user_id=u.id, title="Late report", est_minutes=90,
                   due_at=now() - timedelta(days=3))
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()

    import re as _re
    for focus in ("study", ""):
        reply = conversation.suggestion_reply(db_session, u, focus=focus)
        assert not _re.search(r"-\d+\s*h", reply), f"negative hours leaked: {reply!r}"
        assert not _re.search(r"due in about -", reply), reply
        if "Late report" in reply:
            assert "ago" in reply, f"an overdue item read as upcoming: {reply!r}"


def test_a_greeting_carrying_a_real_request_still_acts(db_session):
    """Stripping the greeting must not swallow the instruction behind it."""
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "hey jocasta, add DSA practice tomorrow at 7pm")
    assert any(c["tool"] == "create_task" and c["ok"] for c in out["calls"]), out["calls"]


def test_the_yo_in_you_is_not_stripped():
    """"you ok?" once became "u ok?" — the greeting alternation lacked a word
    boundary and matched inside the word."""
    assert classify("you ok?")[0] is Intent.CONVERSATION
    assert classify("your notes")[0] is not Intent.CONVERSATION


# ---------------------------------------------------------------- 2. suggestions
JUNK = ["Hello", "hi", "Hi how are you", "Can you add a new course called AI",
        "I like donkey?", "Create a task called test task for tomorrow at 5 pm",
        "ok", "asdf"]


@pytest.mark.parametrize("title", JUNK)
def test_junk_titles_are_recognised(title):
    assert conversation.looks_like_junk(title), title


@pytest.mark.parametrize("title", [
    "Normalization worksheet", "Revise Trees (DSA)", "Submit UX report",
    "Evening workout", "Read chapter 4",
])
def test_real_work_is_not_mistaken_for_junk(title):
    assert not conversation.looks_like_junk(title), title


def test_a_suggestion_never_recommends_junk(db_session):
    """The reported case: an overdue conversational row became the advice."""
    u = _user(db_session)
    for title in ("Create a task called test task for tomorrow at 5 pm", "Hi how are you"):
        db_session.add(Task(user_id=u.id, title=title, status="open",
                            due_at=now() - timedelta(days=3)))
    db_session.add(Task(user_id=u.id, title="Finish the UX report", status="open",
                        due_at=now() - timedelta(days=1)))
    db_session.commit()

    reply = conversation.suggestion_reply(db_session, u)
    assert "test task" not in reply.lower()
    assert "how are you" not in reply.lower()
    assert "UX report" in reply


def test_a_study_question_is_answered_with_study(db_session):
    """"What should I study tonight" must not return the nearest chore."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Take the bins out", status="open",
                        due_at=now() - timedelta(days=2)))
    c = Course(user_id=u.id, name="Database Systems", code="DBMS")
    db_session.add(c); db_session.flush()
    m = CourseModule(user_id=u.id, course_id=c.id, name="Unit I", order=0)
    db_session.add(m); db_session.flush()
    db_session.add(CourseTopic(user_id=u.id, module_id=m.id, name="Normalization", order=0))
    db_session.commit()

    reply = conversation.suggestion_reply(db_session, u, focus="study")
    assert "Normalization" in reply
    assert "bins" not in reply.lower()


def test_study_prioritises_an_urgent_deadline_over_a_loose_topic(db_session):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Pandas", area="DataScience",
                                 state="learning"))
    a = Assignment(user_id=u.id, title="DBMS Assignment", est_minutes=60,
                   due_at=now() + timedelta(hours=10))
    db_session.add(a); db_session.flush()
    materialize.task_for_assignment(db_session, a)
    db_session.commit()

    reply = conversation.suggestion_reply(db_session, u, focus="study")
    assert "DBMS Assignment" in reply


def test_revision_outranks_an_unfinished_topic(db_session):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Pandas", area="DataScience",
                                 state="learning"))
    db_session.add(LearningTopic(user_id=u.id, name="Trees & Graphs", area="DSA",
                                 state="needs_revision"))
    db_session.commit()
    assert "Trees & Graphs" in conversation.suggestion_reply(db_session, u, focus="study")


def test_with_nothing_to_study_it_says_so_and_names_the_goals(db_session):
    u = _user(db_session)
    for title in ("DSA", "Data Science", "Web Development"):
        db_session.add(Goal(user_id=u.id, title=title, status="active"))
    db_session.commit()

    reply = conversation.suggestion_reply(db_session, u, focus="study")
    assert "DSA" in reply and "Web Development" in reply
    assert "pick one" in reply.lower()


def test_with_no_data_at_all_it_admits_it(db_session):
    u = _user(db_session)
    reply = conversation.suggestion_reply(db_session, u, focus="study")
    assert "don't have" in reply.lower() or "nothing" in reply.lower()


def test_a_study_question_writes_nothing(db_session):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Trees", area="DSA",
                                 state="needs_revision"))
    db_session.commit()
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, "what should i study tonight")
    assert out["intent"] == "suggestion"
    assert out["calls"] == []
    assert _tasks(db_session, u) == before


# ---------------------------------------------------------------- 3. wording
@pytest.mark.parametrize("source,category,expected", [
    ("assignment", "College", "deadline"),
    ("learning", "Study", "study session"),
    ("project", "Project", "project task"),
    ("manual", "Personal", "task"),
    ("reminder", "Personal", "reminder"),
])
def test_each_planner_item_is_named_for_what_it_is(db_session, source, category, expected):
    u = _user(db_session)
    t = Task(user_id=u.id, title="Thing", status="open", source=source,
             category=category, due_at=now() + timedelta(hours=3))
    db_session.add(t); db_session.commit(); db_session.refresh(t)

    described = safety.describe(
        [{"tool": "reschedule_task",
          "args": {"task_id": str(t.id), "due_at": (now() + timedelta(hours=5)).isoformat()}}],
        db_session, u)
    assert expected in described[0]["summary"], described[0]["summary"]


def test_moving_a_study_session_is_not_called_a_deadline(db_session):
    """The reported wording bug."""
    u = _user(db_session)
    t = Task(user_id=u.id, title="DSA practice", status="open", source="learning",
             category="Study", due_at=now().replace(hour=7, minute=0))
    db_session.add(t); db_session.commit(); db_session.refresh(t)

    intents = [{"tool": "reschedule_task",
                "args": {"task_id": str(t.id),
                         "due_at": now().replace(hour=8, minute=0).isoformat()}}]
    reason = safety.reason_for(intents, db_session, u)
    assert "deadline" not in reason.lower()
    assert "study session" in reason.lower()
    assert "DSA practice" in reason


def test_the_confirmation_states_both_times(db_session):
    u = _user(db_session)
    t = Task(user_id=u.id, title="DSA practice", status="open", source="learning",
             category="Study", due_at=now().replace(hour=7, minute=0, second=0, microsecond=0))
    db_session.add(t); db_session.commit(); db_session.refresh(t)

    reason = safety.reason_for(
        [{"tool": "reschedule_task",
          "args": {"task_id": str(t.id),
                   "due_at": now().replace(hour=8, minute=0, second=0,
                                           microsecond=0).isoformat()}}],
        db_session, u)
    assert " to " in reason and "from" in reason


# ---------------------------------------------------------------- 3b. titles
@pytest.mark.parametrize("said,expected", [
    ("add DSA practice tomorrow at 7am", "DSA practice"),
    ("add a dentist appointment friday at 3pm", "Dentist appointment"),
    ("schedule gym tonight", "Gym"),
    ("create a new task called laundry", "Laundry"),
    ("put groceries on tomorrow", "Groceries"),
    ("book a haircut saturday", "Haircut"),
    ("add revision monday 9:00", "Revision"),
])
def test_the_instruction_is_not_kept_as_the_title(said, expected):
    """"add DSA practice tomorrow at 7am" creates "DSA practice" — the verb and
    the timing are addressed to JOCasta, not part of the thing's name."""
    from app.jocasta import planner_rules
    calls = planner_rules.plan(said)
    title = calls[0]["args"].get("title", "")
    assert title == expected, f"{said!r} -> {title!r}"


def test_a_reminder_title_is_cleaned_too():
    from app.jocasta import planner_rules
    calls = planner_rules.plan("remind me to submit the form tomorrow at 8am")
    assert calls[0]["tool"] == "create_reminder"
    assert calls[0]["args"]["title"] == "Submit the form"


def test_the_reply_reads_naturally_end_to_end(db_session):
    """The two examples from the report, checked as whole sentences."""
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")
    reply = out["reply"]
    assert reply.startswith("Done — I added DSA practice for tomorrow at"), reply
    assert "create_task" not in reply

    task = db_session.query(Task).filter(Task.user_id == u.id).one()
    moved = orchestrator.run(db_session, u, f"move DSA practice to 8pm")
    if moved.get("confirm_token"):
        applied = orchestrator.confirm(db_session, u, moved["confirm_token"])
        assert "DSA practice is now" in applied["reply"], applied["reply"]
        assert "reschedule" not in applied["reply"]


# ---------------------------------------------------------------- 4. no tool names
def test_no_reply_ever_contains_a_tool_name():
    """A user should never be shown "reschedule_task_by_name"."""
    samples = {
        "create_task": {"title": "DSA practice", "due_at": None},
        "reschedule_task": {"title": "DSA practice", "due_at": None},
        "reschedule_task_by_name": {"title": "DSA practice", "due_at": None},
        "delete_task": {"title": "DSA practice"},
        "complete_task": {"title": "DSA practice", "status": "done"},
        "create_reminder": {"title": "Form", "remind_at": None},
    }
    for tool in REGISTRY:
        res = samples.get(tool, {})
        try:
            reply = _one(tool, res, True, None)
        except Exception:
            continue          # this tool's shape isn't covered by the samples
        assert tool not in reply, f"{tool} leaked into: {reply!r}"
        assert "_" not in reply.replace("—", ""), f"snake_case leaked into: {reply!r}"


def test_an_unrecognised_tool_still_replies_cleanly():
    assert _one("some_future_tool", {}, True, None) == "Done."


def test_every_tool_that_can_run_has_a_module_or_is_read_only():
    """A write with no module mapping means the UI can't offer to show it."""
    for tool in REGISTRY:
        if safety.is_mutation(tool):
            assert tool in TOOL_MODULE, f"{tool} has no module mapping"

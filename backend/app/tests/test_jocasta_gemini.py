"""The Gemini provider seam.

Everything here is offline — `genai.Client` is patched, so no test needs a key
or a network. What is being checked is the part of the migration that is new
code rather than moved code: that our tool schemas are shaped the way the SDK
demands, that a function call the model proposes becomes an ordinary validated
intent dict (and never anything more), and that every provider failure lands on
the deterministic path instead of on the user.
"""
import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.jocasta import brain, llm, orchestrator, planner_llm
from app.jocasta.tools import REGISTRY
from app.models import Task, User
from app.tests.conftest import FakeFunctionCall


def _user(db, email="gemini@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


# ─── the tool schemas the SDK is actually given ────────────────────────────
def test_every_tool_spec_is_accepted_by_the_sdk():
    """Gemini takes a narrower schema than pydantic emits. Building the real
    declaration objects validates all 48 offline — a malformed one would
    otherwise surface as a 400 on a live request and look like a key problem."""
    from google.genai import types

    specs = planner_llm.tool_specs()
    assert len(specs) == len(REGISTRY)
    tool = types.Tool(function_declarations=specs)      # raises if any is invalid
    assert len(tool.function_declarations) == len(REGISTRY)


def test_pydantic_noise_is_stripped_from_the_schema():
    """Titles and defaults are prompt noise: the executor applies defaults when
    it validates, so advertising them only invites the model to restate them."""
    spec = next(s for s in planner_llm.tool_specs() if s["name"] == "create_task")
    schema = spec["parameters_json_schema"]

    assert "title" not in schema
    assert schema["required"] == ["title"]
    for prop in schema["properties"].values():
        assert "title" not in prop
        assert "default" not in prop


def test_an_optional_field_becomes_nullable_not_an_anyof():
    """`X | None` renders as anyOf[X, null], which Gemini has no notion of."""
    spec = next(s for s in planner_llm.tool_specs() if s["name"] == "create_task")
    due = spec["parameters_json_schema"]["properties"]["due_at"]

    assert "anyOf" not in due
    assert due["type"] == "string"
    assert due["nullable"] is True


def test_a_read_only_tool_declares_no_parameters():
    """An empty parameters object is rejected, so the field is omitted."""
    spec = next(s for s in planner_llm.tool_specs() if s["name"] == "get_tasks")
    assert "parameters_json_schema" not in spec
    assert spec["description"]


# ─── a proposal is only ever a proposal ────────────────────────────────────
def test_a_function_call_becomes_an_ordinary_intent_dict(gemini):
    gemini(calls=[FakeFunctionCall("create_task", {"title": "Revise DBMS"})])

    calls = planner_llm.plan("add revise dbms")

    assert calls == [{"tool": "create_task", "args": {"title": "Revise DBMS"}}]


def test_a_tool_the_model_invents_is_dropped(gemini):
    """The executor must never be asked to look up a name that isn't real."""
    gemini(calls=[FakeFunctionCall("drop_all_tables", {"confirm": True}),
                  FakeFunctionCall("get_tasks", {})])

    calls = planner_llm.plan("tidy up")

    assert [c["tool"] for c in calls] == ["get_tasks"]


def test_the_sdk_is_never_allowed_to_execute_a_call(gemini):
    """Proposing a call and running one stay separate steps. If the SDK were
    left to invoke tools itself it would bypass validation, ownership and
    confirmation in one move."""
    sent = gemini(calls=[FakeFunctionCall("get_tasks", {})])
    planner_llm.plan("what's open?")

    afc = sent[0]["config"].automatic_function_calling
    assert afc.disable is True


def test_the_conversational_path_is_offered_no_tools_at_all(gemini):
    sent = gemini("Doing well, thanks.")
    brain.converse("how are you?")

    assert not getattr(sent[0]["config"], "tools", None)
    assert sent[0]["config"].automatic_function_calling.disable is True


def test_a_proposed_write_still_goes_through_confirmation(db_session, gemini, monkeypatch):
    """The model proposing a delete changes nothing on its own — the existing
    safety layer still stops and asks."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Old task", category="Personal"))
    db_session.commit()
    before = db_session.query(Task).filter(Task.user_id == u.id).count()

    monkeypatch.setattr(orchestrator.intent_mod, "classify",
                        lambda t: (orchestrator.Intent.DELETE, "test"))
    gemini(calls=[FakeFunctionCall("delete_task", {"name": "Old task"})])

    out = orchestrator.run(db_session, u, "delete old task")

    assert out["pending"] or out["confirm_token"], "a delete ran without confirmation"
    assert db_session.query(Task).filter(Task.user_id == u.id).count() == before


# ─── failure always lands on the deterministic path ────────────────────────
def test_the_planner_falls_back_when_gemini_is_unavailable(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    assert planner_llm.available() is False

    u = _user(db_session)
    out = orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")

    assert out["planner"] == "rules"
    assert db_session.query(Task).filter(Task.user_id == u.id).count() == 1


@pytest.mark.parametrize("failure, detail", [
    (dict(error=RuntimeError("connection reset")), "connection reset"),
    (dict(error=TimeoutError("deadline exceeded")), "deadline exceeded"),
    (dict(finish_reason="SAFETY"), None),
])
def test_a_planner_failure_never_reaches_the_user(db_session, gemini, failure, detail):
    """Whatever the provider does, the turn still answers — from the rules."""
    gemini(**failure)
    u = _user(db_session)

    out = orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")

    assert out["reply"]
    assert out["planner"] == "rules"
    assert db_session.query(Task).filter(Task.user_id == u.id).count() == 1


def test_a_rate_limit_is_recorded_for_readiness(gemini):
    """429 is the free tier's normal failure. It must be visible as a provider
    problem rather than as JOCasta quietly getting worse."""
    gemini(error=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"))
    assert brain.converse("hello") is None

    state = llm.status()
    assert state["configured"] is True and state["working"] is False
    assert state["using"] == "rules"
    assert "RESOURCE_EXHAUSTED" in state["detail"]


def test_a_planner_failure_is_recorded_too(gemini):
    """Both callers share one provider, so both feed the same health record."""
    gemini(error=RuntimeError("503 UNAVAILABLE"))
    with pytest.raises(Exception):
        planner_llm.plan("anything")

    assert llm.status()["working"] is False
    assert "UNAVAILABLE" in llm.status()["detail"]


# ─── what the model is actually given ──────────────────────────────────────
def test_multi_turn_context_is_carried(db_session, gemini):
    """"Actually, make it one hour" only resolves if the earlier turns went too."""
    sent = gemini("Cutting it to an hour, then.")
    u = _user(db_session)

    orchestrator.run(db_session, u, "I'm tired today.")            # conversation
    orchestrator.run(db_session, u, "I have two hours free.")      # suggestion
    out = orchestrator.run(db_session, u, "Actually, make it one hour.")  # unknown

    assert out["planner"] == "llm"
    contents = sent[-1]["contents"]
    transcript = " ".join(p["text"] for c in contents for p in c["parts"])
    assert "I'm tired today." in transcript
    assert "two hours free" in transcript
    assert "Actually, make it one hour." in transcript
    assert contents[0]["role"] == "user"
    assert {c["role"] for c in contents} <= {"user", "model"}


def test_context_survives_an_action_turn_in_the_middle(db_session, gemini):
    """An explicit instruction is executed deterministically rather than chatted
    about — but it still belongs to the conversation, so the next chat turn can
    see it. Otherwise "did that work?" would have nothing to refer to."""
    sent = gemini("It's on for seven.")
    u = _user(db_session)

    orchestrator.run(db_session, u, "I'm tired today.")
    orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")   # writes
    orchestrator.run(db_session, u, "Actually, make it one hour.")

    transcript = " ".join(p["text"] for c in sent[-1]["contents"] for p in c["parts"])
    assert "add DSA practice tomorrow at 7pm" in transcript


def test_an_explicit_instruction_never_reaches_the_model(db_session, gemini):
    """Deterministic routing still handles clear instructions: no LLM call at
    all, and the reply is the verified one from the executor."""
    sent = gemini(calls=[])
    u = _user(db_session)

    out = orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")

    assert db_session.query(Task).filter(Task.user_id == u.id).count() == 1
    assert not any("system_instruction" in str(r.get("config", "")) and
                   "HOW YOU SOUND" in str(r["config"].system_instruction)
                   for r in sent), "conversation prompt sent for a plain instruction"


def test_history_is_bounded(db_session, gemini):
    """Cheap by construction: enough to resolve a follow-up, not the whole life."""
    sent = gemini("Noted.")
    u = _user(db_session)
    for i in range(12):
        orchestrator.run(db_session, u, f"thought number {i}")

    assert len(sent[-1]["contents"]) <= brain.HISTORY_TURNS + 1


def test_the_model_is_named_from_configuration(gemini, monkeypatch):
    """A retired model id must be fixable from the environment."""
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-9.9-flash")
    sent = gemini("hi")
    brain.converse("hello")
    assert sent[0]["model"] == "gemini-9.9-flash"


def test_the_default_model_is_a_current_flash(gemini):
    default = type(settings)().GEMINI_MODEL
    assert "flash" in default, "a Flash-class model is the intended default"
    assert not default.startswith("gemini-2.0"), "2.0 Flash has been shut down"


def test_the_key_is_never_sent_to_the_frontend(client, auth, gemini, monkeypatch):
    """Server-side only. A leaked key in a JSON body is the whole risk here."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "super-secret-key")
    gemini("All good.", key="super-secret-key")

    bodies = [client.post("/jocasta/message", json={"text": "hey"}, headers=auth).text,
              client.get("/ready").text,
              client.get("/jocasta/context", headers=auth).text]

    for body in bodies:
        assert "super-secret-key" not in body


# ─── client lifetime ───────────────────────────────────────────────────────
def test_the_client_is_reused_across_turns(gemini):
    """Regression: a client built inline and left unreferenced is collected
    mid-request and closes its own connection pool, so the call dies with "the
    client has been closed". Found only by a live call — the fake SDK has no
    such lifecycle — so it is pinned structurally instead."""
    gemini("fine")
    brain.converse("one")
    first = llm.client()
    brain.converse("two")

    assert llm.client() is first, "a fresh client per call reintroduces the bug"


def test_changing_the_key_rebuilds_the_client(gemini, monkeypatch):
    """Reuse must not mean a stale key survives a settings change."""
    gemini("fine")
    first = llm.client()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "a-different-key")

    assert llm.client() is not first


# ─── referent resolution ───────────────────────────────────────────────────
def _tool_row(db, user, tool_name, content):
    from app.models import JOCastaConversation
    db.add(JOCastaConversation(user_id=user.id, role="tool",
                               tool_name=tool_name, content=content))
    db.commit()


def test_a_referent_is_found_under_task_id(db_session):
    """schedule_study materialises a task and reports it as `task_id`. Matching
    only `id` made "move it to 8" resolve to nothing."""
    u = _user(db_session)
    _tool_row(db_session, u, "schedule_study",
              "{'topic': 'Trees & Graphs', 'task_id': "
              "'d3f1c2a4-1111-2222-3333-444455556666', 'due_at': '2026-08-31T19:00:00'}")

    ref = orchestrator._recent_referent(db_session, u)

    assert ref and ref["id"] == "d3f1c2a4-1111-2222-3333-444455556666"
    assert ref["title"] == "Trees & Graphs"


def test_a_listing_is_never_treated_as_a_referent(db_session):
    """get_tasks returns every open task. Taking the first id would point
    "delete that" at an unrelated one — the dangerous version of this bug."""
    u = _user(db_session)
    _tool_row(db_session, u, "get_tasks",
              "[{'id': 'aaaaaaaa-1111-2222-3333-444455556666', 'title': 'DBMS Assignment'}, "
              "{'id': 'bbbbbbbb-1111-2222-3333-444455556666', 'title': 'Evening Workout'}]")

    assert orchestrator._recent_referent(db_session, u) is None


def test_a_listing_does_not_mask_the_real_referent(db_session):
    """A read after a write must not bury what "it" means."""
    u = _user(db_session)
    _tool_row(db_session, u, "create_task",
              "{'id': 'cccccccc-1111-2222-3333-444455556666', 'title': 'DSA practice'}")
    _tool_row(db_session, u, "get_tasks",
              "[{'id': 'aaaaaaaa-1111-2222-3333-444455556666', 'title': 'Something else'}, "
              "{'id': 'bbbbbbbb-1111-2222-3333-444455556666', 'title': 'Another'}]")

    ref = orchestrator._recent_referent(db_session, u)

    assert ref and ref["title"] == "DSA practice"


def test_the_referent_is_given_to_the_model(db_session, gemini):
    """The rule planner proposes a tool that can be patched afterwards; a model
    told nothing about "it" proposes something unrelated instead, and then there
    is nothing left to correct."""
    sent = gemini(calls=[FakeFunctionCall("reschedule_task", {})])
    u = _user(db_session)
    _tool_row(db_session, u, "schedule_study",
              "{'topic': 'Trees & Graphs', 'task_id': "
              "'d3f1c2a4-1111-2222-3333-444455556666', 'due_at': '2026-08-31T19:00:00'}")

    orchestrator.run(db_session, u, "Actually move it to 8 PM.")

    system = sent[0]["config"].system_instruction
    assert "d3f1c2a4-1111-2222-3333-444455556666" in system
    assert "Trees & Graphs" in system


def test_a_time_only_move_keeps_the_existing_day(db_session, gemini):
    """"Move it to 8pm" on a tomorrow item must not resolve 8pm against today
    and quietly drag the item back a day."""
    sent = gemini(calls=[FakeFunctionCall("reschedule_task", {})])
    u = _user(db_session)
    _tool_row(db_session, u, "schedule_study",
              "{'topic': 'Trees & Graphs', 'task_id': "
              "'d3f1c2a4-1111-2222-3333-444455556666', "
              "'due_at': '2026-08-31T19:00:00+00:00'}")

    orchestrator.run(db_session, u, "Actually move it to 8 PM.")

    system = sent[0]["config"].system_instruction
    assert "2026-08-31T19:00:00+00:00" in system
    assert "keep that item's existing date" in system


def test_a_bare_time_reschedule_keeps_the_items_own_day(db_session):
    """The live bug: a session booked for tomorrow 7pm, moved with "make it
    8pm", jumped back to *today* 8pm because a bare time resolves to today."""
    args = {"due_at": "2026-08-30T14:30:00+00:00"}          # today 20:00 IST
    referent = {"id": "x", "title": "Study", "due_at": "2026-08-31T13:30:00+00:00"}

    orchestrator._keep_referent_day(args, referent, "actually make it 8 pm")

    assert args["due_at"].startswith("2026-08-31"), "the day was not preserved"
    assert "14:30" in args["due_at"], "the new time was lost"


def test_naming_a_day_still_wins(db_session):
    """"Move it to tomorrow at 8" must not be dragged back onto the old day."""
    args = {"due_at": "2026-09-02T14:30:00+00:00"}
    referent = {"id": "x", "title": "Study", "due_at": "2026-08-31T13:30:00+00:00"}

    orchestrator._keep_referent_day(args, referent, "move it to wednesday at 8 pm")

    assert args["due_at"].startswith("2026-09-02"), "an explicit day was overridden"


def test_the_referent_reflects_the_live_record_not_the_old_tool_result(db_session):
    """A stored tool result is a snapshot. A second "move it" that re-anchored
    to the snapshot silently kept using the pre-move time."""
    from app.services.timeutils import as_utc
    from datetime import datetime, timezone
    u = _user(db_session)
    t = Task(user_id=u.id, title="Study: Trees & Graphs", category="Learning",
             due_at=datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc))
    db_session.add(t); db_session.commit(); db_session.refresh(t)
    _tool_row(db_session, u, "reschedule_task",
              "{'id': '%s', 'title': 'Study: Trees & Graphs', "
              "'due_at': '2026-08-30T14:30:00+00:00'}" % t.id)   # stale snapshot

    ref = orchestrator._recent_referent(db_session, u)

    assert ref["due_at"].startswith("2026-08-31"), "stale snapshot time was used"

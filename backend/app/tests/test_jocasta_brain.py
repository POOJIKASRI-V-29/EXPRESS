"""The conversational layer.

The language model is always mocked here — no test reaches the network. What
is being checked is the wiring around it: that it receives real context and no
database, that its reply is used when it works, that the deterministic reply is
used when it doesn't, and that it can never cause a write.
"""
import pytest

from app.core.security import hash_password
from app.jocasta import brain, conversation, orchestrator
from app.jocasta.intent import Intent
from app.models import Goal, JOCastaConversation, LearningTopic, Task, User
from app.services.timeutils import now


def _user(db, email="brain@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _tasks(db, user):
    return db.query(Task).filter(Task.user_id == user.id).count()


@pytest.fixture()
def spoke(monkeypatch):
    """Pretend a model is configured, and record exactly what it was given."""
    calls = []

    def fake(message, brief="", history=None, note=""):
        calls.append({"message": message, "brief": brief,
                      "history": history or [], "note": note})
        return "A natural reply."

    monkeypatch.setattr(brain, "available", lambda: True)
    monkeypatch.setattr(brain, "converse", fake)
    return calls


@pytest.fixture()
def silent(monkeypatch):
    """A configured model that fails — the fallback must carry the turn."""
    monkeypatch.setattr(brain, "available", lambda: True)
    monkeypatch.setattr(brain, "converse", lambda *a, **k: None)


# ---------------------------------------------------------------- availability
def test_no_key_means_unavailable(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    assert brain.available() is False
    # And it never pretends: converse returns None rather than a canned line.
    assert brain.converse("hello") is None


def test_without_a_model_the_deterministic_reply_is_used(db_session, monkeypatch):
    monkeypatch.setattr(brain, "available", lambda: False)
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "hey jocasta")
    assert out["reply"]
    assert out["planner"] == "rules"
    assert "not sure what to do" not in out["reply"].lower()


def test_when_the_model_fails_the_turn_still_answers(db_session, silent):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "hey jocasta, how are you?")
    assert out["reply"], "a failed model must not produce an empty turn"
    assert out["planner"] == "rules", "should have fallen back"


def test_a_refusal_falls_back(gemini):
    """A safety finish reason is a normal outcome, not an exception."""
    gemini(text="", finish_reason="SAFETY")
    assert brain.converse("hello", brief="") is None


def test_a_network_error_is_swallowed(gemini):
    gemini(error=RuntimeError("connection reset"))
    assert brain.converse("hello") is None


# ---------------------------------------------------------------- it is used
def test_the_models_reply_is_what_the_user_sees(db_session, spoke):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "hey jocasta, how are you?")
    assert out["reply"] == "A natural reply."
    assert out["planner"] == "llm"
    assert spoke and spoke[0]["message"] == "hey jocasta, how are you?"


@pytest.mark.parametrize("text", [
    "hey jocasta, how are you?", "i'm tired", "thanks", "good night",
    "what should i do tonight", "what should i study", "hmm", "schedule something",
])
def test_conversation_through_the_model_never_writes(db_session, spoke, text):
    u = _user(db_session)
    before = _tasks(db_session, u)
    out = orchestrator.run(db_session, u, text)
    assert out["calls"] == [], f"{text!r} ran tools"
    assert _tasks(db_session, u) == before, f"{text!r} created a record"


def test_the_model_cannot_reach_the_database(db_session, spoke):
    """It is handed text, never a session — checked by inspecting the call."""
    u = _user(db_session)
    orchestrator.run(db_session, u, "what should i do tonight")
    for call in spoke:
        for value in call.values():
            assert not hasattr(value, "query"), "a database session reached the model"
        assert isinstance(call["brief"], str)


# ---------------------------------------------------------------- context
def test_a_suggestion_is_given_real_context(db_session, spoke):
    u = _user(db_session)
    db_session.add(LearningTopic(user_id=u.id, name="Trees & Graphs", area="DSA",
                                 state="needs_revision"))
    db_session.add(Goal(user_id=u.id, title="Crack DSA interviews", status="active"))
    db_session.commit()

    orchestrator.run(db_session, u, "what should i study tonight")
    brief = spoke[-1]["brief"]
    assert "Trees & Graphs" in brief
    assert "Crack DSA interviews" in brief


def test_a_sign_off_is_given_no_context(db_session, spoke):
    """"Good night" must not be answered with a list of overdue work."""
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Overdue thing", status="open",
                        due_at=now() - __import__("datetime").timedelta(days=2)))
    db_session.commit()

    orchestrator.run(db_session, u, "good night")
    call = spoke[-1]
    assert call["brief"] == "", "context was sent for a sign-off"
    assert "do not mention tasks" in call["note"].lower()


def test_thanks_is_light_too(db_session, spoke):
    u = _user(db_session)
    orchestrator.run(db_session, u, "thanks")
    assert spoke[-1]["brief"] == ""


@pytest.mark.parametrize("text,light", [
    ("thanks", True), ("good night", True), ("bye", True), ("ok", True),
    ("hey jocasta", False), ("what should i do", False), ("i'm tired", False),
])
def test_which_turns_carry_context(text, light):
    assert conversation.is_light_turn(text) is light, text


def test_the_brief_states_only_real_records(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Real task", status="open",
                        due_at=now() + __import__("datetime").timedelta(hours=2)))
    db_session.commit()
    brief = conversation.state_brief(db_session, u)
    assert "Real task" in brief
    assert "Imaginary" not in brief


# ---------------------------------------------------------------- multi-turn
def test_recent_turns_are_carried(db_session, spoke):
    u = _user(db_session)
    for role, content in [("user", "i want to study DSA tonight"),
                          ("assistant", "Sure. How much time do you have?")]:
        db_session.add(JOCastaConversation(user_id=u.id, role=role, content=content))
    db_session.commit()

    orchestrator.run(db_session, u, "about two hours")
    history = spoke[-1]["history"]
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert "study DSA tonight" in history[0]["content"]


def test_tool_rows_are_not_sent_as_conversation(db_session, spoke):
    u = _user(db_session)
    db_session.add(JOCastaConversation(user_id=u.id, role="user", content="hi"))
    db_session.add(JOCastaConversation(user_id=u.id, role="tool",
                                       content="{'id': 'abc', 'title': 'x'}",
                                       tool_name="create_task"))
    db_session.commit()

    orchestrator.run(db_session, u, "how are you")
    assert all(h["role"] in ("user", "assistant") for h in spoke[-1]["history"])
    assert not any("create_task" in h["content"] for h in spoke[-1]["history"])


def test_the_conversation_starts_with_a_user_turn():
    """The API rejects a conversation opening with a model message."""
    msgs = brain._contents([{"role": "assistant", "content": "earlier reply"}], "hello")
    assert msgs[0]["role"] == "user"


def test_the_assistant_is_named_model(gemini):
    """Gemini calls the assistant role "model"; sending "assistant" is rejected."""
    msgs = brain._contents([{"role": "user", "content": "hi"},
                            {"role": "assistant", "content": "hello"}], "still there?")
    assert [m["role"] for m in msgs] == ["user", "model", "user"]


def test_consecutive_same_role_turns_are_merged():
    msgs = brain._contents(
        [{"role": "user", "content": "one"}, {"role": "user", "content": "two"}], "three")
    assert [m["role"] for m in msgs] == ["user"]
    assert msgs[0]["parts"][0]["text"] == "one\ntwo\nthree"


# ---------------------------------------------------------------- safety
def test_explicit_actions_still_bypass_the_model_entirely(db_session, spoke):
    """Deterministic routing keeps handling clear instructions — no LLM cost,
    and the reply is the verified one from the executor."""
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "add DSA practice tomorrow at 7pm")
    assert any(c["tool"] == "create_task" and c["ok"] for c in out["calls"])
    assert spoke == [], "the model was called for a plain action"
    assert "DSA practice" in out["reply"]


def test_the_model_is_told_not_to_invent_or_claim_actions():
    """The guardrails live in the system prompt; assert they are present."""
    prompt = brain.SYSTEM.lower()
    assert "never claim you did something" in prompt
    assert "never invent" in prompt or "never guess" in prompt
    assert "only source of facts" in prompt


def test_a_confirmation_still_gates_a_risky_action(db_session, spoke):
    u = _user(db_session)
    t = Task(user_id=u.id, title="DSA practice", status="open",
             due_at=now() + __import__("datetime").timedelta(hours=2))
    db_session.add(t); db_session.commit()

    out = orchestrator.run(db_session, u, "move DSA practice to 8pm")
    assert out["pending"] is not None and out["confirm_token"]
    assert out["calls"] == [], "acted before confirmation"


# ---------------------------------------------------------------- the reported bug
@pytest.mark.parametrize("said", [
    "Hey Ja Costa how are you",          # real speech transcripts of "JOCasta"
    "He Da Costa how are you",
    "hey jacosta how are u",
    "Hey Jata how are you",
    "Hey Ja Costa how are you doing",
])
def test_a_garbled_name_is_still_small_talk(said):
    """Speech recognition rarely gets "JOCasta" right. When the rest of a short
    message is unmistakable small talk, the mangled address must not send the
    turn to UNKNOWN — that is what produced "I'm not sure what to do with that"."""
    from app.jocasta.intent import classify
    intent, why = classify(said)
    assert intent is Intent.CONVERSATION, f"{said!r} -> {intent.value} ({why})"


@pytest.mark.parametrize("said", [
    "hey jocasta add dsa practice tomorrow at 7",
    "delete the dsa task",
    "move it to 8",
])
def test_the_garbled_name_rule_does_not_swallow_instructions(said):
    from app.jocasta.intent import classify
    assert classify(said)[0] is not Intent.CONVERSATION, said


def test_a_garbled_greeting_answers_instead_of_giving_up(db_session, silent):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "Hey Ja Costa how are you")
    assert "not sure what to do with that" not in out["reply"].lower()
    assert out["calls"] == []


# ---------------------------------------------------------------- real path
class _Block:  # retained: the deterministic tests below don't need the SDK
    pass


def test_a_conversational_message_reaches_brain_and_its_reply_is_used(db_session, gemini):
    """With the LLM available, an ordinary conversational turn must go through
    brain.py and come back in the reply. The SDK is patched, not the brain, so
    the real module runs end to end."""
    sent = gemini("Hey — I'm good. What are we working on?")
    u = _user(db_session)

    out = orchestrator.run(db_session, u, "Hey Jocasta, how are you?")

    assert out["reply"] == "Hey — I'm good. What are we working on?"
    assert out["planner"] == "llm", "the reply did not come from the model"
    assert out["intent"] == "conversation"
    assert out["calls"] == []
    assert sent, "no request reached the SDK"
    assert sent[0]["model"], "no model was named"
    assert "JOCasta" in sent[0]["config"].system_instruction, "persona prompt missing"


def test_the_same_holds_through_the_http_route(client, auth, gemini):
    gemini("All good here. What do you need?")
    r = client.post("/jocasta/message", json={"text": "Hey Jocasta, how are you?"},
                    headers=auth)
    assert r.status_code == 200
    assert r.json()["reply"] == "All good here. What do you need?"


def test_a_garbled_name_also_reaches_the_model(db_session, gemini):
    """The speech-recognition fix and the model path must both still hold."""
    gemini("Doing fine. What's up?")
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "Hey Ja Costa how are you")
    assert out["reply"] == "Doing fine. What's up?"
    assert out["planner"] == "llm"


def test_the_voice_transcript_reaches_the_same_brain(db_session, gemini):
    """Voice adds no second pipeline: the transcript is just text on the way in,
    so it lands on exactly the path a typed message takes."""
    sent = gemini("Sleep well.")
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "Hey Jata how are you")   # a real transcript
    assert out["planner"] == "llm"
    assert out["reply"] == "Sleep well."
    assert "Hey Jata how are you" in sent[0]["contents"][-1]["parts"][0]["text"]


# ---------------------------------------------------------------- status honesty
def test_status_separates_configured_from_working(monkeypatch):
    """A key being present is not evidence a call will succeed. Conflating them
    is how a billing problem looks like a wiring problem."""
    from app.core.config import settings
    from app.jocasta import llm

    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(llm, "_last_error", None)
    monkeypatch.setattr(llm, "_last_ok", False)
    s = brain.status()
    assert s["configured"] is False and s["working"] is False and s["using"] == "rules"

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    s = brain.status()
    assert s["configured"] is True and s["working"] is None, "unverified must not read as working"
    assert s["using"] == "unverified"

    monkeypatch.setattr(llm, "_last_error", "ClientError: quota exceeded")
    s = brain.status()
    assert s["configured"] is True and s["working"] is False
    assert "quota" in s["detail"]

    monkeypatch.setattr(llm, "_last_error", None)
    monkeypatch.setattr(llm, "_last_ok", True)
    assert brain.status()["working"] is True


def test_a_failed_call_is_recorded_for_readiness(gemini):
    gemini(error=RuntimeError("quota exceeded for this model"))
    assert brain.converse("hi") is None
    assert "quota exceeded" in (brain.status()["detail"] or "")
    assert brain.status()["working"] is False


def test_an_empty_reply_is_recorded_rather_than_swallowed(gemini):
    """Usually the whole budget went on reasoning. It must be visible in /ready,
    not look like the deterministic layer simply chose to answer."""
    gemini(text="")
    assert brain.converse("hi") is None
    assert brain.status()["working"] is False
    assert "no text" in (brain.status()["detail"] or "")


def test_readiness_reports_the_failure(client, monkeypatch):
    from app.core.config import settings
    from app.jocasta import llm
    monkeypatch.setattr(llm, "_last_error", "ClientError: quota exceeded")
    monkeypatch.setattr(llm, "_last_ok", False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    body = client.get("/ready").json()["checks"]["jocasta_llm"]
    assert body["provider"] == "gemini"
    assert body["configured"] is True
    assert body["working"] is False
    assert body["answering_with"] == "rules"
    assert "quota" in body["detail"]


def test_readiness_makes_no_api_call(client, gemini):
    """A health check must not cost a request — /ready reports last-known state."""
    sent = gemini("should never be asked")
    client.get("/ready")
    assert sent == [], "readiness called the provider"

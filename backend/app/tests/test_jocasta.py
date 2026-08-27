from app.models import User, Memory, Task
from app.core.security import hash_password
from app.jocasta import orchestrator


def _user(db):
    u = User(email="j@express.os", name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_jocasta_creates_reminder(db_session):
    u = _user(db_session)
    out = orchestrator.run(db_session, u, "remind me to wash shoes sunday")
    assert out["planner"] == "rules"
    assert any(c["tool"] == "create_reminder" and c["ok"] for c in out["calls"])
    assert db_session.query(Task).filter(Task.user_id == u.id).count() >= 1


def test_jocasta_saves_and_searches_memory(db_session):
    u = _user(db_session)
    orchestrator.run(db_session, u, "remember that I prefer studying DSA at night")
    assert db_session.query(Memory).filter(Memory.user_id == u.id).count() == 1
    out = orchestrator.run(db_session, u, "what do you remember about DSA")
    call = next(c for c in out["calls"] if c["tool"] == "search_memory")
    assert call["ok"] and len(call["result"]) == 1


def test_jocasta_tools_are_user_scoped(db_session):
    u1, u2 = _user(db_session), User(email="k@express.os", name="Other", hashed_password=hash_password("x"))
    db_session.add(u2); db_session.commit(); db_session.refresh(u2)
    orchestrator.run(db_session, u1, "remember teammates are Aditi and Rohan")
    # u2 searching must not see u1's memory
    out = orchestrator.run(db_session, u2, "what do you remember about Aditi")
    call = next(c for c in out["calls"] if c["tool"] == "search_memory")
    assert call["result"] == []

from datetime import timedelta
from app.models import User, Assignment, Task
from app.core.security import hash_password
from app.services import spider_sense
from app.services.timeutils import now


def _user(db):
    u = User(email="s@express.os", name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_deadline_generates_action_notification(db_session):
    u = _user(db_session)
    db_session.add(Assignment(user_id=u.id, title="DBMS Assignment",
                              due_at=now() + timedelta(hours=10), status="open"))
    db_session.commit()
    spider_sense.scan(db_session, u)
    notifs = spider_sense.active(db_session, u)
    assert any(n.kind == "deadline" and n.level == "action" for n in notifs)


def test_postponed_task_generates_attention(db_session):
    u = _user(db_session)
    db_session.add(Task(user_id=u.id, title="Revise Trees", status="open", postpone_count=3))
    db_session.commit()
    spider_sense.scan(db_session, u)
    assert any(n.kind == "postponed" for n in spider_sense.active(db_session, u))


def test_scan_is_idempotent(db_session):
    u = _user(db_session)
    db_session.add(Assignment(user_id=u.id, title="X", due_at=now() + timedelta(hours=5), status="open"))
    db_session.commit()
    spider_sense.scan(db_session, u)
    spider_sense.scan(db_session, u)  # second scan must not duplicate
    deadline_notifs = [n for n in spider_sense.active(db_session, u) if n.kind == "deadline"]
    assert len(deadline_notifs) == 1

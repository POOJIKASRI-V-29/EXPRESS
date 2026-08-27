"""Spider Sense 2.0: every detector, and the rules that stop it becoming noise."""
from datetime import timedelta

from app.core.security import hash_password
from app.models import (User, Task, Assignment, Course, Exam, Project, LearningTopic,
                        Goal, GoalLink, Habit, HabitLog, Budget, FinanceEntry,
                        Internship, Application, Notification)
from app.services import spider_sense as ss
from app.services import habits as habits_svc
from app.services.timeutils import now, local_today


def _user(db, email="ss@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _keys(signals):
    return {s.dedupe_key.split(":")[0] for s in signals}


def _by_kind(db, user, kind):
    return [n for n in ss.active(db, user) if n.kind == kind]


def test_every_signal_explains_itself_and_suggests_an_action(db_session):
    """The rule that keeps the tray worth reading."""
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="UI/UX Design", attendance=60))
    db_session.add(Assignment(user_id=u.id, title="Overdue essay",
                              due_at=now() - timedelta(days=2), est_minutes=60))
    db_session.add(Budget(user_id=u.id, category="Food", monthly_limit=100))
    db_session.add(FinanceEntry(user_id=u.id, amount=200, category="Food", date=now()))
    db_session.commit()

    ss.scan(db_session, u)
    signals = ss.active(db_session, u)
    assert signals
    for n in signals:
        assert n.title, "a signal needs a title"
        assert n.explanation, f"{n.dedupe_key} raised without explaining why"
        assert n.action_label and n.action_href, f"{n.dedupe_key} suggests no action"
        assert n.source, "a signal must say which detector raised it"
        assert 1 <= n.severity <= 5


def test_signals_are_ordered_most_severe_first(db_session):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Course A", attendance=50))     # action
    h = Habit(user_id=u.id, title="Read", target_per_week=7)                  # info
    db_session.add(h); db_session.flush()
    for d in range(1, 5):
        db_session.add(HabitLog(user_id=u.id, habit_id=h.id,
                                on_date=local_today() - timedelta(days=d)))
    db_session.flush(); habits_svc.recompute(db_session, u, h)
    db_session.commit()

    ss.scan(db_session, u)
    sev = [n.severity for n in ss.active(db_session, u)]
    assert sev == sorted(sev, reverse=True)


def test_deadline_collision_is_detected(db_session):
    u = _user(db_session)
    db_session.add(Assignment(user_id=u.id, title="Essay one",
                              due_at=now() + timedelta(days=3), est_minutes=120))
    db_session.add(Assignment(user_id=u.id, title="Essay two",
                              due_at=now() + timedelta(days=4), est_minutes=120))
    db_session.commit()
    ss.scan(db_session, u)
    hits = _by_kind(db_session, u, "collision")
    assert hits, "two heavy deadlines a day apart should collide"
    assert "of work converging" in hits[0].explanation


def test_unrelated_deadlines_do_not_collide(db_session):
    u = _user(db_session)
    db_session.add(Assignment(user_id=u.id, title="Early",
                              due_at=now() + timedelta(days=1), est_minutes=120))
    db_session.add(Assignment(user_id=u.id, title="Much later",
                              due_at=now() + timedelta(days=9), est_minutes=120))
    db_session.commit()
    ss.scan(db_session, u)
    assert not _by_kind(db_session, u, "collision")


def test_streak_at_risk_is_raised_but_only_once_logged(db_session):
    u = _user(db_session)
    h = Habit(user_id=u.id, title="Morning workout", target_per_week=7)
    db_session.add(h); db_session.flush()
    for d in range(1, 5):
        db_session.add(HabitLog(user_id=u.id, habit_id=h.id,
                                on_date=local_today() - timedelta(days=d)))
    db_session.flush(); habits_svc.recompute(db_session, u, h)
    db_session.commit()

    ss.scan(db_session, u)
    assert _by_kind(db_session, u, "habit"), "a 4-day streak not logged today is worth a nudge"

    db_session.add(HabitLog(user_id=u.id, habit_id=h.id, on_date=local_today()))
    db_session.commit()
    ss.scan(db_session, u)
    assert not _by_kind(db_session, u, "habit"), "logging it must clear the nudge"


def test_short_streaks_are_not_nagged_about(db_session):
    u = _user(db_session)
    h = Habit(user_id=u.id, title="New habit", target_per_week=7)
    db_session.add(h); db_session.flush()
    db_session.add(HabitLog(user_id=u.id, habit_id=h.id,
                            on_date=local_today() - timedelta(days=1)))
    db_session.flush(); habits_svc.recompute(db_session, u, h)
    db_session.commit()
    ss.scan(db_session, u)
    assert not _by_kind(db_session, u, "habit")


def test_resolved_signals_stop_nagging(db_session):
    """A condition that no longer holds must clear itself."""
    u = _user(db_session)
    c = Course(user_id=u.id, name="Slipping", attendance=60)
    db_session.add(c); db_session.commit()
    ss.scan(db_session, u)
    assert _by_kind(db_session, u, "attendance")

    c.attendance = 95
    db_session.commit()
    ss.scan(db_session, u)
    assert not _by_kind(db_session, u, "attendance")


def test_scan_is_idempotent(db_session):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Slipping", attendance=60))
    db_session.commit()
    ss.scan(db_session, u)
    first = db_session.query(Notification).filter(Notification.user_id == u.id).count()
    for _ in range(4):
        ss.scan(db_session, u)
    assert db_session.query(Notification).filter(Notification.user_id == u.id).count() == first


def test_a_dismissed_signal_stays_dismissed(db_session):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Slipping", attendance=60))
    db_session.commit()
    ss.scan(db_session, u)
    n = _by_kind(db_session, u, "attendance")[0]
    n.acknowledged = True
    db_session.commit()

    ss.scan(db_session, u)
    assert not _by_kind(db_session, u, "attendance"), "a dismissed signal must not come back"


def test_signal_volume_is_capped(db_session):
    u = _user(db_session)
    for i in range(60):
        db_session.add(Course(user_id=u.id, name=f"Course {i}", attendance=40))
    db_session.commit()
    ss.scan(db_session, u)
    assert len(ss.active(db_session, u)) <= ss.MAX_ACTIVE_SIGNALS


def test_one_broken_detector_does_not_blind_the_others(db_session, monkeypatch):
    u = _user(db_session)
    db_session.add(Course(user_id=u.id, name="Slipping", attendance=60))
    db_session.commit()

    def explode(db, user):
        raise RuntimeError("detector boom")

    monkeypatch.setattr(ss, "DETECTORS", (explode, ss._detect_attendance))
    ss.scan(db_session, u)
    assert _by_kind(db_session, u, "attendance"), "a failing detector suppressed a working one"


def test_signals_stay_scoped_to_their_owner(db_session):
    a, b = _user(db_session, "sa@x.com"), _user(db_session, "sb@x.com")
    db_session.add(Course(user_id=a.id, name="A's course", attendance=40))
    db_session.commit()
    ss.scan(db_session, a)
    ss.scan(db_session, b)
    assert ss.active(db_session, a)
    assert not ss.active(db_session, b)

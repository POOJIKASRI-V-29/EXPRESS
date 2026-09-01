"""JOCasta operating the course workspace through real tools."""
from app.core.security import hash_password
from app.jocasta import orchestrator, safety
from app.models import Course, CourseModule, CourseTopic, Task, User
from app.services import courses as course_svc


def _user(db, email="col@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _course(db, user, name="Database Management Systems", attended=23, total=28, code="DBMS"):
    # Students enter the shorthand they actually use as the course code; the
    # resolver searches code as well as name, so "DBMS" resolves exactly.
    c = Course(user_id=user.id, name=name, code=code)
    course_svc.set_counts(c, attended, total)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _call(out, tool):
    return next((c for c in out["calls"] if c["tool"] == tool), None)


# ---------------------------------------------------------------- attendance
def test_attendance_is_counted_not_typed():
    assert course_svc.pct(23, 28) == 82
    assert course_svc.pct(0, 0) == 0          # no data, not 0% risk
    assert course_svc.pct(5, 0) == 0


def test_jocasta_records_an_attended_class(db_session):
    u = _user(db_session)
    _course(db_session, u)
    out = orchestrator.run(db_session, u, "i attended dbms today")
    call = _call(out, "mark_attendance")
    assert call and call["ok"]
    assert (call["result"]["attended_classes"], call["result"]["total_classes"]) == (24, 29)
    assert "24 of 29" in out["reply"]


def test_jocasta_records_a_missed_class_and_attendance_falls(db_session):
    u = _user(db_session)
    c = _course(db_session, u, attended=20, total=20)
    out = orchestrator.run(db_session, u, "i missed database management systems")
    call = _call(out, "mark_attendance")
    assert call and call["ok"]
    # A missed class still counts as held — that is why the percentage drops.
    assert (call["result"]["attended_classes"], call["result"]["total_classes"]) == (20, 21)
    assert call["result"]["attendance"] == 95


def test_overwriting_attendance_asks_first(db_session):
    """Correcting a record outright is destructive, so it is gated."""
    u = _user(db_session)
    _course(db_session, u)
    assert safety.risk_of("set_attendance") == safety.SENSITIVE
    verdict = safety.classify([{"tool": "set_attendance", "args": {}}])
    assert verdict["needs_confirmation"]


def test_attendance_cannot_be_pushed_past_reality(db_session):
    u = _user(db_session)
    c = _course(db_session, u, attended=0, total=0)
    course_svc.set_counts(c, 50, 10)
    assert c.attended_classes == 10 and c.attendance == 100
    course_svc.set_counts(c, -5, -5)
    assert c.attended_classes == 0 and c.total_classes == 0


# ---------------------------------------------------------------- concepts
def _with_topics(db, user, course, names=("ER model", "Normalization", "Keys")):
    m = CourseModule(user_id=user.id, course_id=course.id, name="Unit I", order=0)
    db.add(m); db.flush()
    for i, n in enumerate(names):
        db.add(CourseTopic(user_id=user.id, module_id=m.id, name=n, order=i))
    db.commit()
    return m


def test_jocasta_ticks_a_concept_and_progress_follows(db_session):
    u = _user(db_session)
    c = _course(db_session, u)
    _with_topics(db_session, u, c)

    out = orchestrator.run(db_session, u, "mark normalization as complete in database management systems")
    call = _call(out, "complete_topic")
    assert call and call["ok"]
    assert call["result"]["done"] is True
    assert call["result"]["course_progress"] == 33      # 1 of 3, counted
    assert "33% covered" in out["reply"]


def test_completing_something_falls_back_from_tasks_to_concepts(db_session):
    """"I finished binary trees" should find a concept when no task matches."""
    u = _user(db_session)
    c = _course(db_session, u)
    _with_topics(db_session, u, c, names=("Binary trees", "Graphs"))

    out = orchestrator.run(db_session, u, "i completed binary trees")
    call = _call(out, "complete_task_by_name")
    assert call and call["ok"], call
    assert call["result"]["kind"] == "concept"
    assert call["result"]["title"] == "Binary trees"


def test_an_open_task_wins_over_a_same_named_concept(db_session):
    """Tasks carry deadlines, so they are the more urgent reading."""
    u = _user(db_session)
    c = _course(db_session, u)
    _with_topics(db_session, u, c, names=("Binary trees",))
    db_session.add(Task(user_id=u.id, title="Binary trees", status="open"))
    db_session.commit()

    out = orchestrator.run(db_session, u, "i finished binary trees")
    call = _call(out, "complete_task_by_name")
    assert call["ok"] and call["result"]["kind"] == "task"


def test_concepts_do_not_match_across_courses(db_session):
    u = _user(db_session)
    dbms = _course(db_session, u, "Database Management Systems")
    ml = _course(db_session, u, "Machine Learning")
    _with_topics(db_session, u, dbms, names=("Normalization",))
    _with_topics(db_session, u, ml, names=("Regularization",))

    out = orchestrator.run(db_session, u, "mark normalization as complete in machine learning")
    call = _call(out, "complete_topic")
    assert call and not call["ok"], "matched a concept from the wrong course"


def test_jocasta_cannot_touch_another_users_course(db_session):
    a, b = _user(db_session, "ca@x.com"), _user(db_session, "cb@x.com")
    _course(db_session, a, "Private Course", code="PRIV")
    out = orchestrator.run(db_session, b, "i attended private course")
    call = _call(out, "mark_attendance")
    assert call and not call["ok"]


# ---------------------------------------------------------------- drive
def test_jocasta_saves_a_drive_link(db_session):
    u = _user(db_session)
    _course(db_session, u)
    out = orchestrator.run(
        db_session, u,
        "add google drive to dbms https://drive.google.com/drive/folders/xyz")
    call = _call(out, "set_course_drive")
    assert call and call["ok"]
    assert call["result"]["drive_url"].endswith("/xyz")
    assert db_session.query(Course).filter(Course.user_id == u.id).first().drive_url


def test_asking_how_a_course_is_going_reads_only(db_session):
    u = _user(db_session)
    c = _course(db_session, u)
    _with_topics(db_session, u, c)
    out = orchestrator.run(db_session, u, "how is my dbms going")
    call = _call(out, "get_course")
    assert call and call["ok"]
    assert all(c_["tool"].startswith("get_") for c_ in out["calls"])
    assert "82%" in out["reply"] and "23/28" in out["reply"]


def test_course_shorthand_resolves(db_session):
    """Two routes to the shorthand students actually use: the course code they
    typed ("DBMS"), and mechanically-derivable initials ("ML")."""
    u = _user(db_session)
    _course(db_session, u, "Database Management Systems")
    _course(db_session, u, "Machine Learning", attended=18, total=20, code="CS310")

    out = orchestrator.run(db_session, u, "i attended ml today")
    call = _call(out, "mark_attendance")
    assert call and call["ok"] and call["result"]["course"] == "Machine Learning"


def test_ambiguous_initials_resolve_to_nothing_rather_than_guess(db_session):
    u = _user(db_session)
    _course(db_session, u, "Machine Learning", code="")
    _course(db_session, u, "Modern Literature", code="")
    out = orchestrator.run(db_session, u, "i attended ml today")
    call = _call(out, "mark_attendance")
    assert call and not call["ok"], "picked one of two equally plausible courses"


# ---------------------------------------------------------------- voice parity
# Voice has no command system of its own: a transcript is text, and it enters
# `/jocasta/message` exactly as typing does. These cover the phrasing people
# actually speak, which is looser than what they type.
#
# The browser half (SpeechRecognition/SpeechSynthesis) has no automated test —
# there is no frontend test runner in this project, and faking the speech APIs
# would prove nothing. It is verified manually; see the README.
def test_spoken_phrasing_reaches_the_same_tools(db_session):
    u = _user(db_session)
    _course(db_session, u)
    _with_topics(db_session, u,
                 db_session.query(Course).filter(Course.user_id == u.id).first())

    spoken = [
        ("i attended dbms today", "mark_attendance"),
        ("i missed dbms", "mark_attendance"),
        ("mark er model as complete in dbms", "complete_topic"),
        ("how is my dbms going", "get_course"),
        ("what's due", "get_deadlines"),
    ]
    for said, expected in spoken:
        out = orchestrator.run(db_session, u, said)
        assert _call(out, expected), f"{said!r} did not reach {expected}: {out['calls']}"


def test_a_spoken_destructive_request_still_asks_first(db_session):
    """Voice must not become a way around the confirmation gate."""
    u = _user(db_session)
    _course(db_session, u)
    out = orchestrator.run(db_session, u, "set my dbms attendance to 40 out of 50")
    if any(c["tool"] == "set_attendance" for c in out.get("calls", [])):
        raise AssertionError("a sensitive tool ran without confirmation")
    # Either it asked, or the rules planner did not route it — never silent action.
    assert out.get("pending") is not None or not out["calls"] or \
        all(safety.risk_of(c["tool"]) != safety.SENSITIVE for c in out["calls"])

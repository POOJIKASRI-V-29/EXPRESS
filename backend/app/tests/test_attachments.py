"""Attachments: real extraction, honest failure, and no write without consent.

Every PDF here is built byte-by-byte by `pdf_fixture`, so nothing about the
parsing is stubbed — pypdf opens these exactly as it would a real file.
"""
import io

import pytest

from app.core.security import hash_password
from app.jocasta import attachment as flow, orchestrator, safety
from app.models import Class, Course, CourseModule, CourseTopic, User
from app.services import attachments, syllabus as syllabus_svc, timetable as timetable_svc
from app.services import courses as course_svc
from app.tests.pdf_fixture import SYLLABUS_LINES, TIMETABLE_LINES, make_pdf


def _user(db, email="att@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _course(db, user, name, code=""):
    c = Course(user_id=user.id, name=name, code=code)
    course_svc.set_counts(c, 0, 0)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _att(lines=None, **kw):
    return attachments.read(make_pdf(lines or TIMETABLE_LINES, **kw),
                            "timetable.pdf", "application/pdf")


# ---------------------------------------------------------------- extraction
def test_a_real_pdf_is_read():
    att = _att()
    assert att.kind == "pdf" and att.pages == 1
    assert "Monday" in att.text and "Database Management Systems" in att.text


def test_plain_text_is_read():
    att = attachments.read(b"Monday\n10:00-11:00 DBMS Room AB-201",
                           "tt.txt", "text/plain")
    assert att.kind == "text" and "Monday" in att.text


@pytest.mark.parametrize("data,name,ctype,expect", [
    (b"", "x.pdf", "application/pdf", "empty"),
    (b"not a pdf at all", "x.pdf", "application/pdf", "couldn't open"),
    (b"\x89PNG\r\n\x1a\n", "shot.png", "image/png", "can't read images"),
    (b"MZ\x90\x00", "app.exe", "application/octet-stream", "PDFs and plain text"),
])
def test_unreadable_files_explain_themselves(data, name, ctype, expect):
    with pytest.raises(attachments.UnreadableAttachment) as e:
        attachments.read(data, name, ctype)
    assert expect.lower() in str(e.value).lower()


def test_a_scanned_pdf_says_so_rather_than_reporting_an_empty_timetable():
    """The failure mode that matters: a valid PDF with no text layer must not
    look like a timetable that happened to contain nothing."""
    with pytest.raises(attachments.UnreadableAttachment) as e:
        attachments.read(make_pdf([], with_text=False), "scan.pdf", "application/pdf")
    msg = str(e.value).lower()
    assert "scan" in msg or "image" in msg
    assert "no classes" not in msg


def test_an_oversized_file_is_refused():
    with pytest.raises(attachments.UnreadableAttachment) as e:
        attachments.read(b"%PDF" + b"0" * (attachments.MAX_BYTES + 1), "big.pdf", "application/pdf")
    assert "larger than" in str(e.value)


# ---------------------------------------------------------------- parsing
def test_timetable_fields_are_separated_correctly():
    classes, skipped = timetable_svc.parse(_att().text)
    assert len(classes) == 5 and not skipped
    first = classes[0]
    assert (first.day, first.start_time, first.end_time) == ("Monday", "10:00", "11:00")
    assert first.course == "Database Management Systems"
    assert first.code == "DBMS"
    assert first.room == "AB-201"


@pytest.mark.parametrize("line,expected", [
    ("Monday 09:00-10:30 AI310 Machine Learning Room TT 402", "TT 402"),
    ("Monday 09:00-10:30 CS301 Data Structures Hall 3A", "3A"),
    ("Monday 09:00-10:30 CS303 Database Systems Lab B", "B"),
    ("Monday 09:00-10:30 DBMS Database Systems Room AB-201", "AB-201"),
])
def test_two_token_room_names_survive(line, expected):
    """"Room TT 402" must not truncate to "TT" — the room is the whole label."""
    att = attachments.read(make_pdf([line]), "t.pdf", "application/pdf")
    classes, _ = timetable_svc.parse(att.text)
    assert classes and classes[0].room == expected, classes[0].as_dict()


def test_missing_fields_are_left_empty_not_invented():
    att = attachments.read(
        make_pdf(["Friday", "15:00-16:00 Ethics"]), "t.pdf", "application/pdf")
    classes, _ = timetable_svc.parse(att.text)
    assert len(classes) == 1
    c = classes[0]
    assert c.course == "Ethics"
    assert c.room == "" and c.faculty == "" and c.section == ""


def test_a_time_with_no_day_is_reported_not_guessed():
    att = attachments.read(make_pdf(["10:00-11:00 Floating class"]), "t.pdf", "application/pdf")
    classes, skipped = timetable_svc.parse(att.text)
    assert classes == [] and len(skipped) == 1


def test_repeated_rows_collapse():
    lines = ["Monday", "10:00-11:00 DBMS Database Management Systems",
             "Monday", "10:00-11:00 DBMS Database Management Systems"]
    classes, _ = timetable_svc.parse(
        attachments.read(make_pdf(lines), "t.pdf", "application/pdf").text)
    assert len(classes) == 1


def test_syllabus_structure_is_extracted():
    out = syllabus_svc.parse(_att(SYLLABUS_LINES).text)
    assert out["course_name"] == "Database Management Systems"
    assert out["course_code"] == "DBMS"
    assert [m["name"] for m in out["modules"]] == [
        "Unit I — Database Fundamentals", "Unit II — Design", "Unit III — Transactions"]
    assert out["modules"][0]["topics"] == ["DBMS architecture", "ER model", "Relational model"]


# ---------------------------------------------------------------- interpretation
def test_the_instruction_decides_what_the_file_is_for(db_session):
    """The same document means different things depending on what was asked."""
    signals, _c, _o = flow.analyse(_att())
    assert flow.decide("add this timetable", signals) == "timetable"
    assert flow.decide("what does this say", signals) == "answer"
    assert flow.decide("", signals) == "answer"


def test_content_decides_when_the_instruction_is_only_an_action(db_session):
    tt, _c, _o = flow.analyse(_att())
    syl, _c2, _o2 = flow.analyse(_att(SYLLABUS_LINES))
    assert flow.decide("add this to my planner", tt) == "timetable"
    assert flow.decide("add this", syl) == "course"


def test_reading_a_file_never_writes(db_session):
    u = _user(db_session)
    out = flow.build(db_session, u, "what does this say", _att())
    assert out["kind"] == "talk"
    assert db_session.query(Class).count() == 0


# ---------------------------------------------------------------- course matching
def test_classes_match_existing_courses_by_code_and_name(db_session):
    u = _user(db_session)
    dbms = _course(db_session, u, "Database Management Systems", "DBMS")
    ml = _course(db_session, u, "Machine Learning", "CS310")
    classes, _ = timetable_svc.parse(_att().text)
    plan = timetable_svc.plan_import(db_session, u, classes)
    matched = {r["matched_course"] for r in plan["to_add"]}
    assert matched == {"Database Management Systems", "Machine Learning"}
    assert plan["unmatched"] == []


def test_unknown_courses_are_not_silently_created(db_session):
    u = _user(db_session)
    _course(db_session, u, "Machine Learning", "CS310")
    classes, _ = timetable_svc.parse(_att().text)
    plan = timetable_svc.plan_import(db_session, u, classes)
    assert "DBMS" in plan["unmatched_names"]

    timetable_svc.apply_import(db_session, u, classes)
    assert db_session.query(Course).filter(Course.user_id == u.id).count() == 1


# ---------------------------------------------------------------- write path
def test_nothing_is_written_before_confirmation(db_session):
    u = _user(db_session)
    _course(db_session, u, "Database Management Systems", "DBMS")
    _course(db_session, u, "Machine Learning", "CS310")

    out = flow.build(db_session, u, "add this timetable to my planner", _att())
    assert out["kind"] == "confirm"
    assert out["actions"] and out["reply"]
    assert db_session.query(Class).count() == 0, "wrote before asking"


def test_confirmation_creates_the_real_classes(db_session):
    u = _user(db_session)
    _course(db_session, u, "Database Management Systems", "DBMS")
    _course(db_session, u, "Machine Learning", "CS310")
    classes, _ = timetable_svc.parse(_att().text)

    result = timetable_svc.apply_import(db_session, u, classes)
    assert result["added"] == 5
    rows = db_session.query(Class).filter(Class.user_id == u.id).all()
    assert len(rows) == 5
    monday = [r for r in rows if r.day_of_week == 0]
    assert {r.start_time for r in monday} == {"10:00", "14:00"}
    assert any(r.room == "AB-201" for r in rows)


def test_importing_twice_does_not_duplicate(db_session):
    u = _user(db_session)
    _course(db_session, u, "Database Management Systems", "DBMS")
    _course(db_session, u, "Machine Learning", "CS310")
    classes, _ = timetable_svc.parse(_att().text)

    timetable_svc.apply_import(db_session, u, classes)
    second = timetable_svc.apply_import(db_session, u, classes)
    assert second["added"] == 0
    assert second["skipped_duplicates"] == 5
    assert db_session.query(Class).filter(Class.user_id == u.id).count() == 5


def test_replacing_reports_the_cost_before_doing_it(db_session):
    u = _user(db_session)
    _course(db_session, u, "Database Management Systems", "DBMS")
    _course(db_session, u, "Machine Learning", "CS310")
    classes, _ = timetable_svc.parse(_att().text)
    timetable_svc.apply_import(db_session, u, classes)

    out = flow.build(db_session, u, "replace my timetable with this", _att())
    assert out["kind"] == "confirm"
    assert out["risk"] == safety.SENSITIVE
    assert "remove your current 5 slot(s)" in " ".join(a["summary"] for a in out["actions"])
    assert db_session.query(Class).count() == 5, "replace happened before confirmation"

    result = timetable_svc.apply_import(db_session, u, classes, replace=True)
    assert result["removed"] == 5 and result["added"] == 5
    assert db_session.query(Class).filter(Class.user_id == u.id).count() == 5


def test_course_structure_needs_a_named_course(db_session):
    u = _user(db_session)
    out = flow.build(db_session, u, "create the course from this syllabus", _att(SYLLABUS_LINES))
    assert out["kind"] == "talk"
    assert "which course" in out["reply"].lower()
    assert db_session.query(CourseModule).count() == 0


def test_course_structure_previews_then_applies(db_session):
    u = _user(db_session)
    c = _course(db_session, u, "Database Management Systems", "DBMS")
    out = flow.build(db_session, u, "build the modules from this syllabus", _att(SYLLABUS_LINES))
    assert out["kind"] == "confirm"
    assert db_session.query(CourseModule).count() == 0

    token = safety.sign_payload(u.id, out["payload"], audience="jocasta-confirm")
    done = orchestrator.confirm(db_session, u, token)
    assert "3 module" in done["reply"]
    assert db_session.query(CourseModule).filter(CourseModule.course_id == c.id).count() == 3
    assert db_session.query(CourseTopic).filter(CourseTopic.user_id == u.id).count() == 7


# ---------------------------------------------------------------- end to end
def test_upload_then_instruct_then_confirm(client, auth, db_session):
    """The whole journey through the API, as the UI drives it."""
    user = db_session.query(User).first()
    _course(db_session, user, "Database Management Systems", "DBMS")
    _course(db_session, user, "Machine Learning", "CS310")

    up = client.post("/jocasta/attachments",
                     files={"file": ("timetable.pdf", io.BytesIO(make_pdf(TIMETABLE_LINES)),
                                     "application/pdf")}, headers=auth)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["found"]["classes"] == 5 and body["attachment_token"]

    said = client.post("/jocasta/message",
                       json={"text": "add this timetable to my planner",
                             "attachment_token": body["attachment_token"]},
                       headers=auth).json()
    assert said["pending"] and said["confirm_token"]
    assert client.get("/planner", headers=auth).json()["days"]  # nothing written yet
    assert db_session.query(Class).filter(Class.user_id == user.id).count() == 0

    done = client.post("/jocasta/confirm",
                       json={"confirm_token": said["confirm_token"]}, headers=auth).json()
    assert "Added 5" in done["reply"]
    assert db_session.query(Class).filter(Class.user_id == user.id).count() == 5


def test_an_unreadable_upload_is_rejected_with_a_reason(client, auth):
    r = client.post("/jocasta/attachments",
                    files={"file": ("shot.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
                    headers=auth)
    assert r.status_code == 422
    assert "images" in r.json()["detail"].lower()


def test_an_attachment_token_is_bound_to_its_user(client, auth):
    other = client.post("/auth/register", json={"email": "at@x.com", "password": "pass1234"}).json()
    client.cookies.clear()
    up = client.post("/jocasta/attachments",
                     files={"file": ("t.pdf", io.BytesIO(make_pdf(TIMETABLE_LINES)),
                                     "application/pdf")}, headers=auth).json()
    stolen = client.post("/jocasta/message",
                         json={"text": "add this timetable",
                               "attachment_token": up["attachment_token"]},
                         headers={"Authorization": f"Bearer {other['access_token']}"}).json()
    assert stolen["pending"] is None
    assert "isn't valid" in stolen["reply"]


def test_asking_for_a_timetable_with_no_file_asks_for_one(client, auth):
    out = client.post("/jocasta/message",
                      json={"text": "update my timetable"}, headers=auth).json()
    assert out["pending"] is None
    assert "attach" in out["reply"].lower()

"""Planner and College CRUD — the operations that let a real timetable be typed in.

The point of this phase was that the user could correct their own data without
asking JOCasta, so most of what is checked here is the plain HTTP surface: a
course can be made, edited, and removed; a weekly class can be scheduled, moved
and deleted; and a class that exists in College turns up in Planner on the right
day. The JOCasta equivalents are checked too, because a natural-language path
that skips the safety layer would be worse than no path at all.
"""
import pytest

from app.core.security import hash_password
from app.jocasta import orchestrator, safety
from app.models import Class, Course, CourseModule, CourseTopic, Task, User
from app.services import courses as course_svc
from app.services import planner as planner_svc
from app.services.timeutils import local_today


def _user(db, email="crud@express.os"):
    u = User(email=email, name="Pooji", hashed_password=hash_password("x"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def _module(client, auth, course_id, name):
    """Add a module and return its id.

    The endpoint answers with the whole course workspace rather than the new
    module, so the id has to come out of module_list.
    """
    ws = client.post(f"/college/courses/{course_id}/modules",
                     json={"name": name}, headers=auth).json()
    return next(m["id"] for m in ws["module_list"] if m["name"] == name)


def _course(client, auth, **kw):
    body = {"name": "Database Systems", "code": "DBMS"} | kw
    r = client.post("/college/courses", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ─── course CRUD ───────────────────────────────────────────────────────────
def test_a_course_can_be_created_with_real_figures(client, auth):
    c = _course(client, auth, faculty="Dr Rao", credits=4,
                attended_classes=42, total_classes=50)

    assert c["name"] == "Database Systems" and c["code"] == "DBMS"
    assert c["faculty"] == "Dr Rao" and c["credits"] == 4
    assert (c["attended_classes"], c["total_classes"]) == (42, 50)
    assert c["attendance"] == 84


def test_only_a_name_is_required(client, auth):
    r = client.post("/college/courses", json={"name": "Operating Systems"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["total_classes"] == 0


def test_a_course_can_be_edited(client, auth):
    c = _course(client, auth)

    r = client.patch(f"/college/courses/{c['id']}", headers=auth, json={
        "name": "Database Management Systems", "code": "DBMS-2",
        "faculty": "Dr Iyer", "credits": 3,
        "drive_url": "https://drive.google.com/drive/folders/abc"})

    assert r.status_code == 200
    out = r.json()
    assert out["name"] == "Database Management Systems"
    assert out["credits"] == 3 and out["faculty"] == "Dr Iyer"
    assert out["drive_url"].endswith("/abc")


def test_editing_attendance_stays_mathematically_honest(client, auth):
    """One Edit dialog saves everything, so the route has to apply the same
    clamping the attendance endpoints do — otherwise it could store 60/50."""
    c = _course(client, auth, attended_classes=10, total_classes=20)

    r = client.patch(f"/college/courses/{c['id']}", headers=auth,
                     json={"attended_classes": 60, "total_classes": 50})

    out = r.json()
    assert out["attended_classes"] <= out["total_classes"], "attended exceeded held"
    assert out["attendance"] <= 100


def test_attendance_percentage_is_attended_over_held():
    assert course_svc.pct(42, 50) == 84
    assert course_svc.pct(1, 3) == 33


def test_zero_held_is_no_data_not_zero_percent(client, auth):
    """A brand new course has held nothing. 0% would read as a failing record;
    the UI shows "— no classes yet" off the back of these figures."""
    c = _course(client, auth)

    assert c["total_classes"] == 0
    assert course_svc.pct(0, 0) == 0        # the number is meaningless...
    r = client.get("/college", headers=auth)
    row = next(x for x in r.json()["courses"] if x["id"] == c["id"])
    assert row["has_attendance_data"] is False, "must be flagged as 'no data', not 0%"


def test_a_course_delete_reports_what_it_will_take(client, auth):
    c = _course(client, auth)
    mid = _module(client, auth, c["id"], "Normalization")
    client.post(f"/college/modules/{mid}/topics", json={"name": "BCNF"}, headers=auth)
    client.post("/college/classes", headers=auth,
                json={"course_id": c["id"], "day_of_week": 0, "start_time": "09:00"})

    impact = client.get(f"/college/courses/{c['id']}/impact", headers=auth).json()

    assert impact["course"] == "Database Systems"
    assert impact["modules"] == 1 and impact["concepts"] == 1
    assert impact["classes"] == 1


def test_deleting_a_course_removes_its_structure(client, auth, db_session):
    c = _course(client, auth)
    _module(client, auth, c["id"], "Normalization")
    mid = _module(client, auth, c["id"], "Transactions")
    client.post(f"/college/modules/{mid}/topics", json={"name": "ACID"}, headers=auth)
    client.post("/college/classes", headers=auth,
                json={"course_id": c["id"], "day_of_week": 0, "start_time": "09:00"})

    assert client.delete(f"/college/courses/{c['id']}", headers=auth).status_code == 204

    assert client.get(f"/college/courses/{c['id']}", headers=auth).status_code == 404
    assert db_session.query(CourseModule).filter(CourseModule.course_id == c["id"]).count() == 0
    assert db_session.query(CourseTopic).filter(CourseTopic.module_id == mid).count() == 0
    assert db_session.query(Class).filter(Class.course_id == c["id"]).count() == 0


def test_deleting_a_course_does_not_touch_unrelated_planner_items(client, auth, db_session):
    """The rule that matters most here: an evening the user planned is theirs,
    not a property of the course record."""
    c = _course(client, auth)
    client.post("/tasks", headers=auth,
                json={"title": "Gym", "category": "Personal"})
    client.post("/tasks", headers=auth,
                json={"title": "Read DBMS notes", "category": "Study"})
    before = client.get("/tasks", headers=auth).json()

    client.delete(f"/college/courses/{c['id']}", headers=auth)

    after = client.get("/tasks", headers=auth).json()
    assert {t["title"] for t in after} == {t["title"] for t in before}


# ─── ownership ─────────────────────────────────────────────────────────────
def test_a_course_cannot_be_touched_by_another_account(client, auth, db_session):
    c = _course(client, auth)
    other = client.post("/auth/register", json={
        "email": "intruder@express.os", "password": "secret123", "name": "X"}).json()
    theirs = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get(f"/college/courses/{c['id']}", headers=theirs).status_code == 404
    assert client.patch(f"/college/courses/{c['id']}", json={"name": "Hijacked"},
                        headers=theirs).status_code == 404
    assert client.delete(f"/college/courses/{c['id']}", headers=theirs).status_code == 404
    assert client.get(f"/college/courses/{c['id']}", headers=auth).json()["name"] \
        == "Database Systems", "the owner's course was altered"


# ─── the weekly timetable ──────────────────────────────────────────────────
def test_a_weekly_class_can_be_scheduled_moved_and_removed(client, auth):
    c = _course(client, auth)

    cl = client.post("/college/classes", headers=auth, json={
        "course_id": c["id"], "day_of_week": 0,
        "start_time": "09:00", "end_time": "10:30", "room": "AB-201"}).json()
    assert cl["day_of_week"] == 0 and cl["start_time"] == "09:00"

    moved = client.patch(f"/college/classes/{cl['id']}", headers=auth,
                         json={"start_time": "10:00", "end_time": "11:30"}).json()
    assert moved["start_time"] == "10:00"
    assert moved["day_of_week"] == 0, "the day changed when only a time was given"
    assert moved["room"] == "AB-201", "an untouched field was cleared"

    assert client.delete(f"/college/classes/{cl['id']}", headers=auth).status_code == 204


@pytest.mark.parametrize("day", [-1, 7, 99])
def test_an_impossible_weekday_is_rejected(client, auth, day):
    c = _course(client, auth)
    r = client.post("/college/classes", headers=auth,
                    json={"course_id": c["id"], "day_of_week": day})
    assert r.status_code == 422


def test_a_scheduled_class_appears_in_the_planner(client, auth):
    """The whole point of the chain: College → scheduled class → Planner."""
    c = _course(client, auth, code="DBMS", faculty="Dr Rao")
    today = local_today().weekday()
    client.post("/college/classes", headers=auth, json={
        "course_id": c["id"], "day_of_week": today,
        "start_time": "09:00", "end_time": "10:30", "room": "AB-201"})

    day = client.get("/planner/day/0", headers=auth).json()
    items = day["items"] if isinstance(day, dict) and "items" in day else day
    classes = [i for i in items if i.get("category") == planner_svc.CLASS]

    assert classes, "the scheduled class did not reach the planner"
    it = classes[0]
    assert "Database Systems" in it["title"] or it.get("code") == "DBMS"
    assert it.get("course_id") == c["id"]


def test_a_course_with_no_scheduled_class_invents_nothing(client, auth):
    _course(client, auth)

    day = client.get("/planner/day/0", headers=auth).json()
    items = day["items"] if isinstance(day, dict) and "items" in day else day

    assert [i for i in items if i.get("category") == planner_svc.CLASS] == []


# ─── planner item CRUD ─────────────────────────────────────────────────────
def test_a_planner_item_can_be_created_edited_and_deleted(client, auth):
    made = client.post("/tasks", headers=auth, json={
        "title": "DSA practice", "category": "Study",
        "due_at": "2026-09-02T13:30:00+00:00", "est_minutes": 60}).json()
    assert made["title"] == "DSA practice"

    edited = client.patch(f"/tasks/{made['id']}", headers=auth, json={
        "title": "DSA practice (graphs)", "est_minutes": 90,
        "due_at": "2026-09-02T14:30:00+00:00"}).json()
    assert edited["title"] == "DSA practice (graphs)"
    assert edited["est_minutes"] == 90
    assert edited["due_at"].startswith("2026-09-02T14:30")

    assert client.delete(f"/tasks/{made['id']}", headers=auth).status_code == 204
    assert made["id"] not in [t["id"] for t in client.get("/tasks", headers=auth).json()]


def test_the_planner_offers_exactly_the_agreed_categories():
    assert planner_svc.CATEGORIES == ["Task", "Study", "Project", "Goal", "Personal"]
    assert planner_svc.CLASS not in planner_svc.CATEGORIES, \
        "a class comes from the timetable, not from the add dialog"


@pytest.mark.parametrize("sent, stored", [
    ("Study", "Study"), ("study", "Study"), ("Goal", "Goal"), ("goal", "Goal"),
    ("Project", "Project"), ("Personal", "Personal"),
    ("learning", "Study"), ("coursework", "Task"),
    ("nonsense-category", "Task"),           # unknown falls back, never rejected
])
def test_category_validation(sent, stored):
    assert planner_svc.normalise(sent) == stored


def test_a_class_is_not_completable_like_a_task(client, auth):
    """Classes are attended or missed. Marking one "done" would put a fake row
    in the task queue for something that is not a task."""
    c = _course(client, auth)
    today = local_today().weekday()
    client.post("/college/classes", headers=auth, json={
        "course_id": c["id"], "day_of_week": today, "start_time": "09:00"})

    day = client.get("/planner/day/0", headers=auth).json()
    items = day["items"] if isinstance(day, dict) and "items" in day else day
    cl = next(i for i in items if i.get("category") == planner_svc.CLASS)

    assert cl.get("can_complete") is not True
    assert cl.get("course_id"), "a class must carry its course so attendance can be marked"


# ─── the same things through JOCasta ───────────────────────────────────────
def _run(db, user, text):
    return orchestrator.run(db, user, text)


def test_jocasta_can_create_a_course(db_session):
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc

    out = tools.create_course(db_session, u, sc.CreateCourseArgs(
        name="Database Systems", code="DBMS", credits=4,
        attended_classes=42, total_classes=50))

    assert out["attendance"] == 84
    c = db_session.query(Course).filter(Course.user_id == u.id).one()
    assert c.name == "Database Systems" and c.credits == 4


def test_jocasta_can_schedule_a_class(db_session):
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))

    out = tools.schedule_class(db_session, u, sc.ScheduleClassArgs(
        course="DBMS", day_of_week=0, start_time="09:00", end_time="10:30"))

    assert out["day"] == "Monday" and out["start_time"] == "09:00"
    assert db_session.query(Class).filter(Class.user_id == u.id).count() == 1


def test_jocasta_moving_a_class_keeps_the_untouched_fields(db_session):
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))
    tools.schedule_class(db_session, u, sc.ScheduleClassArgs(
        course="DBMS", day_of_week=0, start_time="09:00", end_time="10:30", room="AB-201"))

    out = tools.reschedule_class(db_session, u, sc.RescheduleClassArgs(
        course="DBMS", start_time="10:00"))

    assert out["start_time"] == "10:00" and out["day"] == "Monday"
    assert db_session.query(Class).filter(Class.user_id == u.id).one().room == "AB-201"


def test_jocasta_refuses_to_guess_between_two_slots(db_session):
    """"Move my DBMS class" with two of them is ambiguous — asking beats acting."""
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))
    for day in (0, 2):
        tools.schedule_class(db_session, u, sc.ScheduleClassArgs(
            course="DBMS", day_of_week=day, start_time="09:00"))

    with pytest.raises(ValueError, match="say which one"):
        tools.reschedule_class(db_session, u, sc.RescheduleClassArgs(
            course="DBMS", start_time="10:00"))

    assert db_session.query(Class).filter(Class.user_id == u.id).count() == 2


def test_jocasta_course_deletion_is_gated_on_confirmation(db_session, gemini):
    """Natural language must not be a way around the safety layer."""
    from app.tests.conftest import FakeFunctionCall
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))

    gemini(calls=[FakeFunctionCall("delete_course", {"course": "DBMS"})])
    out = _run(db_session, u, "Delete Database Systems.")

    assert out["pending"] or out["confirm_token"], "a course was deleted without asking"
    assert db_session.query(Course).filter(Course.user_id == u.id).count() == 1


def test_jocasta_class_deletion_is_gated_too(db_session, gemini):
    from app.tests.conftest import FakeFunctionCall
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))
    tools.schedule_class(db_session, u, sc.ScheduleClassArgs(course="DBMS", day_of_week=0))

    gemini(calls=[FakeFunctionCall("delete_class", {"course": "DBMS"})])
    out = _run(db_session, u, "Remove that class.")

    assert out["pending"] or out["confirm_token"]
    assert db_session.query(Class).filter(Class.user_id == u.id).count() == 1


@pytest.mark.parametrize("tool", ["delete_course", "delete_class", "reschedule_class",
                                  "update_course", "set_attendance"])
def test_the_destructive_course_tools_ask_first(tool):
    assert safety.risk_of(tool) == safety.SENSITIVE
    assert safety.classify([{"tool": tool, "args": {}}])["needs_confirmation"] is True


def test_scheduling_a_class_does_not_need_confirmation():
    """Adding a slot removes nothing — asking every time would be noise."""
    assert safety.risk_of("schedule_class") == safety.WRITE
    assert safety.classify([{"tool": "schedule_class", "args": {}}])[
        "needs_confirmation"] is False


def test_jocasta_can_set_attendance_after_confirmation(db_session):
    u = _user(db_session)
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Database Systems", code="DBMS"))

    tools.set_attendance(db_session, u, sc.SetAttendanceArgs(
        course="DBMS", attended_classes=42, total_classes=50))

    c = db_session.query(Course).filter(Course.user_id == u.id).one()
    assert (c.attended_classes, c.total_classes, c.attendance) == (42, 50, 84)


def test_a_tool_cannot_reach_another_users_course(db_session):
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    mine = _user(db_session, "mine@express.os")
    theirs = _user(db_session, "theirs@express.os")
    tools.create_course(db_session, theirs, sc.CreateCourseArgs(name="Their Course", code="TC"))

    with pytest.raises(ValueError):
        tools.delete_course(db_session, mine, sc.CourseNameArgs(course="TC"))

    assert db_session.query(Course).filter(Course.user_id == theirs.id).count() == 1


# ─── the deterministic path ────────────────────────────────────────────────
# The free Gemini tier allows 20 requests a day, so the rules planner — not the
# model — is what handles most real use. Every phrase the brief asked for is
# pinned here so College works whether or not the LLM is reachable.
from app.jocasta import planner_rules


@pytest.mark.parametrize("said, tool, expected", [
    ("Add Database Systems to my courses.", "create_course", {"name": "Database systems"}),
    ("Add a course called Machine Learning", "create_course", {"name": "Machine learning"}),
    ("Delete Database Systems from my courses", "delete_course", {"course": "database systems"}),
    ("delete the course Machine Learning", "delete_course", {"course": "machine learning"}),
    ("Set my DBMS attendance to 42 out of 50.", "set_attendance",
     {"course": "dbms", "attended_classes": 42, "total_classes": 50}),
    ("Add DBMS class Monday at 9 AM.", "schedule_class",
     {"course": "dbms", "day_of_week": 0, "start_time": "09:00"}),
    ("Move my DBMS class to 10 AM.", "reschedule_class",
     {"course": "dbms", "start_time": "10:00"}),
    ("Remove that DBMS class", "delete_class", {"course": "dbms"}),
])
def test_the_college_phrases_work_without_the_model(said, tool, expected):
    calls = planner_rules.plan(said)
    assert calls, f"nothing proposed for {said!r}"
    assert calls[0]["tool"] == tool
    for k, v in expected.items():
        assert calls[0]["args"].get(k) == v, f"{k} was {calls[0]['args'].get(k)!r}"


def test_a_weekday_and_room_are_both_read():
    call = planner_rules.plan("Add OS class Wednesday at 2 pm in AB-201")[0]
    assert call["tool"] == "schedule_class"
    assert call["args"]["day_of_week"] == 2
    assert call["args"]["start_time"] == "14:00"
    assert call["args"]["room"] == "AB-201"


def test_a_study_block_keeps_its_topic():
    """The topic leads the sentence here, so "study (.+)" would capture the
    time instead — and stripping the article "a" would turn DSA into DS."""
    call = planner_rules.plan("Add DSA study tomorrow at 7 PM.")[0]
    assert call["tool"] == "schedule_study"
    assert call["args"]["topic"] == "dsa"


@pytest.mark.parametrize("said, tool", [
    ("What is my attendance?", "get_college"),      # a question stays a question
    ("delete the gym task", "delete_task"),          # not a course
    ("add DSA practice tomorrow at 7pm", "create_task"),   # not a study block
])
def test_the_new_rules_do_not_swallow_existing_phrases(said, tool):
    assert planner_rules.plan(said)[0]["tool"] == tool


def test_zero_held_courses_are_left_out_of_the_average(client, auth):
    """A course with nothing held has no attendance. Averaging it in as 0%
    reports a failing record where there is simply no record."""
    _course(client, auth, code="DBMS", attended_classes=42, total_classes=50)
    _course(client, auth, name="Machine Learning", code="ML")   # nothing held

    body = client.get("/college", headers=auth).json()

    assert body["attendance"] == 84, "the empty course dragged the average down"
    assert [c["code"] for c in body["courses"] if c["at_risk"]] == []


def test_jocasta_does_not_call_a_new_course_at_risk(db_session):
    from app.jocasta import tools
    from app.jocasta import schemas as sc
    u = _user(db_session)
    tools.create_course(db_session, u, sc.CreateCourseArgs(
        name="Database Systems", code="DBMS", attended_classes=42, total_classes=50))
    tools.create_course(db_session, u, sc.CreateCourseArgs(name="Machine Learning", code="ML"))

    out = tools.get_college(db_session, u, sc.EmptyArgs())

    assert out["attendance"] == 84
    assert "Machine Learning" not in out["at_risk"]
    ml = next(c for c in out["courses"] if c["name"] == "Machine Learning")
    assert ml["attendance"] is None and ml["classes_held"] == 0


def test_adding_to_a_collection_is_a_write_not_a_lookup():
    """"…to my courses" made READ fire first, so the write guard stripped
    create_course and nothing happened."""
    from app.jocasta import intent as intent_mod

    i, _ = intent_mod.classify("Add Database Systems to my courses")
    assert i is intent_mod.Intent.CREATE and intent_mod.may_write(i)

    i, _ = intent_mod.classify("What courses do I have?")
    assert not intent_mod.may_write(i), "a question became a write"

"""Exams and calendar entries are correctable from the Planner.

The bug: the Planner renders Edit/Delete on `editable`, and only tasks carried
it. An exam like "CAT-2 Window" therefore appeared with no controls at all and
could not be fixed without going through JOCasta. Classes stay uneditable here
on purpose — they belong to the timetable and are managed on their course.
"""
import pytest

from app.models import AcademicEvent, Class, Course, Exam
from app.services import planner as planner_svc


def _items(client, auth, offset=0):
    body = client.get(f"/planner/day/{offset}", headers=auth).json()
    return body["items"] if isinstance(body, dict) and "items" in body else body


def _exam(client, auth, when, title="CAT-2 Window", **kw):
    r = client.post("/college/exams", headers=auth,
                    json={"title": title, "date": when, "type": "cat",
                          "room": "AB-201"} | kw)
    assert r.status_code == 201, r.text
    return r.json()


def _event(client, auth, when, title="Mid-sem break", **kw):
    r = client.post("/college/events", headers=auth,
                    json={"title": title, "date": when, "type": "break"} | kw)
    assert r.status_code == 201, r.text
    return r.json()


def _today_at(client, auth, hhmm="14:00"):
    """An ISO instant inside today's planner window."""
    day = client.get("/planner/day/0", headers=auth).json()
    date = day["date"] if isinstance(day, dict) and "date" in day else None
    assert date, "planner day payload has no date"
    return f"{date[:10]}T{hhmm}:00+00:00"


# ─── the payload the Planner renders from ──────────────────────────────────
def test_an_exam_is_editable_in_the_planner(client, auth):
    when = _today_at(client, auth)
    ex = _exam(client, auth, when)

    it = next(i for i in _items(client, auth) if i["id"] == ex["id"])

    assert it["kind"] == "exam"
    assert it["editable"] is True, "an exam had no Edit/Delete controls"
    assert it["movable"] is False, "an exam must not be draggable like a task"
    assert it["can_complete"] is False


def test_an_event_is_editable_in_the_planner(client, auth):
    when = _today_at(client, auth)
    ev = _event(client, auth, when)

    it = next(i for i in _items(client, auth) if i["id"] == ev["id"])

    assert it["kind"] == "event"
    assert it["editable"] is True
    assert it["movable"] is False
    assert it["can_complete"] is False


def test_a_class_stays_uneditable_in_the_planner(client, auth):
    """Classes are managed on their course, not corrected from the timetable."""
    from app.services.timeutils import local_today
    c = client.post("/college/courses", json={"name": "Database Systems", "code": "DBMS"},
                    headers=auth).json()
    client.post("/college/classes", headers=auth, json={
        "course_id": c["id"], "day_of_week": local_today().weekday(),
        "start_time": "09:00", "end_time": "10:30"})

    it = next(i for i in _items(client, auth) if i["kind"] == "class")

    assert it["editable"] is False
    assert it["movable"] is False


def test_an_exam_carries_what_the_edit_dialog_needs(client, auth):
    when = _today_at(client, auth)
    ex = _exam(client, auth, when)

    it = next(i for i in _items(client, auth) if i["id"] == ex["id"])

    assert it["date"], "no date to prefill the edit dialog with"
    assert it["exam_type"] == "cat"
    assert it["room"] == "AB-201"


# ─── editing ───────────────────────────────────────────────────────────────
def test_an_exam_can_be_corrected(client, auth):
    ex = _exam(client, auth, _today_at(client, auth))

    r = client.patch(f"/college/exams/{ex['id']}", headers=auth, json={
        "title": "CAT-2 (rescheduled)", "room": "CB-105", "type": "internal"})

    assert r.status_code == 200, r.text
    out = r.json()
    assert out["title"] == "CAT-2 (rescheduled)"
    assert out["room"] == "CB-105" and out["type"] == "internal"


def test_moving_an_exam_leaves_its_other_fields_alone(client, auth):
    ex = _exam(client, auth, _today_at(client, auth))

    out = client.patch(f"/college/exams/{ex['id']}", headers=auth,
                       json={"date": "2026-09-15T09:00:00+00:00"}).json()

    assert out["date"].startswith("2026-09-15")
    assert out["title"] == "CAT-2 Window", "an untouched field was cleared"
    assert out["room"] == "AB-201"


def test_an_event_can_be_corrected(client, auth):
    ev = _event(client, auth, _today_at(client, auth))

    out = client.patch(f"/college/events/{ev['id']}", headers=auth, json={
        "title": "Mid-semester break", "type": "holiday",
        "end_date": "2026-09-20T00:00:00+00:00"}).json()

    assert out["title"] == "Mid-semester break"
    assert out["type"] == "holiday"
    assert out["end_date"].startswith("2026-09-20")


# ─── deleting ──────────────────────────────────────────────────────────────
def test_an_exam_can_be_deleted(client, auth, db_session):
    ex = _exam(client, auth, _today_at(client, auth))

    assert client.delete(f"/college/exams/{ex['id']}", headers=auth).status_code == 204

    assert db_session.query(Exam).filter(Exam.id == ex["id"]).count() == 0
    assert ex["id"] not in [i["id"] for i in _items(client, auth)]


def test_an_event_can_be_deleted(client, auth, db_session):
    ev = _event(client, auth, _today_at(client, auth))

    assert client.delete(f"/college/events/{ev['id']}", headers=auth).status_code == 204

    assert db_session.query(AcademicEvent).filter(AcademicEvent.id == ev["id"]).count() == 0


def test_deleting_an_exam_leaves_tasks_alone(client, auth):
    """The Planner used to call deleteTask for anything editable. An exam id
    sent to the task endpoint must never remove somebody's task."""
    ex = _exam(client, auth, _today_at(client, auth))
    client.post("/tasks", headers=auth, json={"title": "Revise trees", "category": "Study"})
    before = [t["title"] for t in client.get("/tasks", headers=auth).json()]

    client.delete(f"/college/exams/{ex['id']}", headers=auth)

    assert [t["title"] for t in client.get("/tasks", headers=auth).json()] == before


def test_an_exam_id_is_not_a_task_id(client, auth):
    """The wrong-endpoint case, made explicit: the task route must not accept it."""
    ex = _exam(client, auth, _today_at(client, auth))

    r = client.delete(f"/tasks/{ex['id']}", headers=auth)

    assert r.status_code == 404
    assert client.get(f"/planner/day/0", headers=auth).status_code == 200


# ─── ownership ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", ["exams", "events"])
def test_another_account_cannot_touch_them(client, auth, kind):
    when = _today_at(client, auth)
    row = (_exam(client, auth, when) if kind == "exams" else _event(client, auth, when))
    other = client.post("/auth/register", json={
        "email": f"intruder-{kind}@express.os", "password": "secret123", "name": "X"}).json()
    theirs = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.patch(f"/college/{kind}/{row['id']}", json={"title": "Hijacked"},
                        headers=theirs).status_code == 404
    assert client.delete(f"/college/{kind}/{row['id']}", headers=theirs).status_code == 404

    still = next(i for i in _items(client, auth) if i["id"] == row["id"])
    assert still["title"] == row["title"], "the owner's row was altered"

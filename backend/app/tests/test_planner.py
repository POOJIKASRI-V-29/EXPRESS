"""Planner as an everyday schedule: create, edit, delete, categorise, complete."""
from datetime import datetime, timedelta, timezone

from app.services import planner as planner_svc
from app.services.timeutils import start_of_local_day


def at(hours: int) -> str:
    """An instant inside today's local window, so it lands on today's page."""
    return (start_of_local_day(0) + timedelta(hours=hours)).isoformat()


def _today(client, auth):
    return client.get("/planner", headers=auth).json()["today"]


def _find(day, title):
    return next((i for i in day["items"] if i["title"] == title), None)


# ---------------------------------------------------------------- categories
def test_categories_are_offered_and_normalised(client, auth):
    body = client.get("/planner", headers=auth).json()
    assert body["categories"] == planner_svc.CATEGORIES

    made = client.post("/tasks", json={"title": "Read a chapter", "category": "study",
                                       "due_at": at(10)}, headers=auth).json()
    assert made["category"] == "Study", "category should normalise to the canonical name"


def test_legacy_categories_map_without_rewriting_rows(client, auth):
    """Older rows keep their stored value; the planner shows the current name."""
    made = client.post("/tasks", json={"title": "Old row", "category": "Routine",
                                       "due_at": at(11)}, headers=auth).json()
    item = _find(_today(client, auth), "Old row")
    assert item["category"] == "Personal"       # displayed
    assert planner_svc.canonical("Routine") == "Personal"


def test_source_wins_over_stored_category(client, auth):
    """A task materialised from a project is project work whatever it says."""
    p = client.post("/projects", json={"name": "EXPRESS"}, headers=auth).json()
    client.post(f"/projects/{p['id']}/tasks",
                json={"title": "Wire the planner", "due_at": at(14)}, headers=auth)
    item = _find(_today(client, auth), "Wire the planner")
    assert item and item["category"] == "Project"
    assert item["source"] == "project"


# ---------------------------------------------------------------- create
def test_creating_a_dated_item_puts_it_on_the_day(client, auth):
    r = client.post("/tasks", json={"title": "Dentist", "category": "Personal",
                                    "due_at": at(9), "est_minutes": 45}, headers=auth)
    assert r.status_code == 201
    item = _find(_today(client, auth), "Dentist")
    assert item and item["est_minutes"] == 45 and item["editable"] is True


def test_an_undated_item_goes_to_unscheduled(client, auth):
    client.post("/tasks", json={"title": "Someday thing"}, headers=auth)
    body = client.get("/planner", headers=auth).json()
    assert any(u["title"] == "Someday thing" for u in body["unscheduled"])
    assert not _find(body["today"], "Someday thing")


def test_scheduling_an_unscheduled_item_moves_it_onto_the_day(client, auth):
    t = client.post("/tasks", json={"title": "Float"}, headers=auth).json()
    client.post(f"/planner/schedule/{t['id']}", json={"due_at": at(16)}, headers=auth)
    body = client.get("/planner", headers=auth).json()
    assert not any(u["title"] == "Float" for u in body["unscheduled"])
    assert _find(body["today"], "Float")


# ---------------------------------------------------------------- edit
def test_every_field_a_user_can_see_is_editable(client, auth):
    t = client.post("/tasks", json={"title": "Typo hree", "category": "Task",
                                    "due_at": at(10), "est_minutes": 30}, headers=auth).json()
    fixed = client.patch(f"/tasks/{t['id']}", json={
        "title": "Typo here", "category": "Study", "est_minutes": 60,
        "due_at": at(15), "meta": "with notes",
    }, headers=auth).json()
    assert fixed["title"] == "Typo here"
    assert fixed["category"] == "Study"
    assert fixed["est_minutes"] == 60
    assert fixed["meta"] == "with notes"
    item = _find(_today(client, auth), "Typo here")
    assert item["time"] != "--:--"


def test_editing_a_time_is_not_counted_as_a_postponement(client, auth):
    """Fixing a mistyped time should not make Spider Sense think work is being
    avoided — that is what /reschedule is for."""
    t = client.post("/tasks", json={"title": "Mistyped", "due_at": at(9)}, headers=auth).json()
    edited = client.patch(f"/tasks/{t['id']}", json={"due_at": at(11)}, headers=auth).json()
    assert edited["postpone_count"] == 0

    moved = client.post(f"/tasks/{t['id']}/reschedule", json={"due_at": at(13)},
                        headers=auth).json()
    assert moved["postpone_count"] == 1


# ---------------------------------------------------------------- delete
def test_items_can_be_deleted(client, auth):
    t = client.post("/tasks", json={"title": "Delete me", "due_at": at(10)}, headers=auth).json()
    assert client.delete(f"/tasks/{t['id']}", headers=auth).status_code == 204
    assert not _find(_today(client, auth), "Delete me")
    assert client.delete(f"/tasks/{t['id']}", headers=auth).status_code == 404


def test_deleting_a_project_task_from_the_planner_keeps_the_project_work(client, auth):
    """The planner entry is a view of the work, not the work itself."""
    p = client.post("/projects", json={"name": "EXPRESS"}, headers=auth).json()
    p = client.post(f"/projects/{p['id']}/tasks",
                    json={"title": "Ship it", "due_at": at(12)}, headers=auth).json()
    mirrored = _find(_today(client, auth), "Ship it")

    client.delete(f"/tasks/{mirrored['id']}", headers=auth)
    still_there = client.get(f"/projects/{p['id']}", headers=auth).json()
    assert [t["title"] for t in still_there["tasks"]] == ["Ship it"]


def test_one_user_cannot_delete_anothers_item(client, auth):
    other = client.post("/auth/register", json={"email": "pd@x.com", "password": "pass1234"}).json()
    client.cookies.clear()
    theirs = {"Authorization": f"Bearer {other['access_token']}"}
    t = client.post("/tasks", json={"title": "Mine", "due_at": at(10)}, headers=auth).json()
    assert client.delete(f"/tasks/{t['id']}", headers=theirs).status_code == 404
    assert _find(_today(client, auth), "Mine")


# ---------------------------------------------------------------- complete
def test_completion_semantics_differ_by_kind(client, auth):
    """A task completes; a class is attended or missed. They are not the same
    action and the planner must not flatten them into one checkbox."""
    t = client.post("/tasks", json={"title": "Finish me", "due_at": at(10)}, headers=auth).json()
    assert client.post(f"/tasks/{t['id']}/complete", headers=auth).json()["status"] == "done"

    c = client.post("/college/courses", json={"name": "DBMS", "attended_classes": 5,
                                              "total_classes": 5}, headers=auth).json()
    marked = client.post(f"/college/courses/{c['id']}/attendance",
                         json={"attended": True}, headers=auth).json()
    assert marked["total_classes"] == 6      # a class is attended, not "completed"


def test_a_class_is_not_editable_or_movable_from_the_planner(client, auth):
    """Timetable slots belong to College; the planner shows them, it doesn't own them."""
    import datetime as _dt
    c = client.post("/college/courses", json={"name": "DBMS"}, headers=auth).json()
    client.post("/college/classes", json={"course_id": c["id"],
                                          "day_of_week": _dt.date.today().weekday(),
                                          "start_time": "09:00", "end_time": "10:30"},
                headers=auth)
    cls = next(i for i in _today(client, auth)["items"] if i["kind"] == "class")
    assert cls["movable"] is False
    assert cls["category"] == "Class"
    assert cls.get("editable") is not True

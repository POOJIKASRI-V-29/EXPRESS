"""Every module: real persistence, real derivation, and user scoping."""
from datetime import datetime, timezone, timedelta


def iso(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat()


# ---------------------------------------------------------------- college
def test_college_course_timetable_and_attendance(client, auth):
    c = client.post("/college/courses", json={"name": "Database Systems", "code": "CS303",
                                              "attended_classes": 23, "total_classes": 28},
                    headers=auth)
    assert c.status_code == 201
    cid = c.json()["id"]
    assert c.json()["attendance"] == 82           # 23/28 = 82.14 -> 82

    cl = client.post("/college/classes", json={"course_id": cid, "day_of_week": 2,
                                               "start_time": "09:00", "end_time": "10:30"},
                     headers=auth)
    assert cl.status_code == 201
    before = client.get("/college", headers=auth).json()
    assert any(t["course"] == "Database Systems" for t in before["timetable"])

    # A missed class still counts as held — that is why attendance falls.
    missed = client.post(f"/college/courses/{cid}/attendance",
                         json={"attended": False}, headers=auth).json()
    assert (missed["attended_classes"], missed["total_classes"]) == (23, 29)
    assert missed["attendance"] == 79

    attended = client.post(f"/college/courses/{cid}/attendance",
                           json={"attended": True}, headers=auth).json()
    assert (attended["attended_classes"], attended["total_classes"]) == (24, 30)
    assert attended["attendance"] == 80


def test_attendance_can_be_undone_and_corrected(client, auth):
    cid = client.post("/college/courses", json={"name": "OS", "attended_classes": 10,
                                                "total_classes": 10}, headers=auth).json()["id"]
    client.post(f"/college/courses/{cid}/attendance", json={"attended": False}, headers=auth)
    undone = client.post(f"/college/courses/{cid}/attendance/undo",
                         json={"attended": False}, headers=auth).json()
    assert (undone["attended_classes"], undone["total_classes"]) == (10, 10)

    fixed = client.patch(f"/college/courses/{cid}/attendance",
                         json={"attended_classes": 18, "total_classes": 20},
                         headers=auth).json()
    assert fixed["attendance"] == 90

    # Attended can never exceed held.
    clamped = client.patch(f"/college/courses/{cid}/attendance",
                           json={"attended_classes": 99, "total_classes": 20},
                           headers=auth).json()
    assert clamped["attended_classes"] == 20 and clamped["attendance"] == 100


def test_a_course_with_no_classes_held_is_not_at_risk(client, auth):
    """0% because nothing has happened yet is "no data", not a warning."""
    client.post("/college/courses", json={"name": "Brand New"}, headers=auth)
    row = client.get("/college", headers=auth).json()["courses"][0]
    assert row["total_classes"] == 0
    assert row["has_attendance_data"] is False
    assert row["at_risk"] is False
    assert not [s for s in client.get("/spider-sense", headers=auth).json()
                if s["kind"] == "attendance"]


def test_course_modules_topics_and_derived_progress(client, auth):
    cid = client.post("/college/courses", json={"name": "DBMS"}, headers=auth).json()["id"]
    ws = client.post(f"/college/courses/{cid}/modules",
                     json={"name": "Module 1 — Fundamentals"}, headers=auth).json()
    assert ws["modules"] == 1 and ws["progress"] == 0
    mid = ws["module_list"][0]["id"]

    for name in ("ER model", "Relational model", "Normalization", "Keys"):
        ws = client.post(f"/college/modules/{mid}/topics", json={"name": name},
                         headers=auth).json()
    assert ws["topics_total"] == 4 and ws["progress"] == 0
    assert ws["next_module"] == "Module 1 — Fundamentals"

    first = ws["module_list"][0]["topics"][0]["id"]
    ws = client.post(f"/college/topics/{first}/toggle", headers=auth).json()
    assert ws["topics_done"] == 1 and ws["progress"] == 25   # counted, not stored

    ws = client.post(f"/college/topics/{first}/toggle", headers=auth).json()
    assert ws["topics_done"] == 0 and ws["progress"] == 0    # and it unticks

    # Completion survives a reload — it is persisted, not local state.
    again = client.get(f"/college/courses/{cid}", headers=auth).json()
    assert again["topics_total"] == 4 and again["topics_done"] == 0


def test_bulk_structure_creation_is_explicit(client, auth):
    """The shape a confirmed syllabus proposal lands on."""
    cid = client.post("/college/courses", json={"name": "DBMS"}, headers=auth).json()["id"]
    ws = client.post(f"/college/courses/{cid}/structure", json={"modules": [
        {"name": "Unit I", "topics": ["ER model", "Keys"]},
        {"name": "Unit II", "topics": ["Normalization"]},
    ]}, headers=auth).json()
    assert ws["modules"] == 2 and ws["topics_total"] == 3
    assert [m["name"] for m in ws["module_list"]] == ["Unit I", "Unit II"]

    # Re-running appends rather than silently wiping.
    ws = client.post(f"/college/courses/{cid}/structure",
                     json={"modules": [{"name": "Unit III", "topics": []}]},
                     headers=auth).json()
    assert ws["modules"] == 3

    # ...unless replacement is asked for explicitly.
    ws = client.post(f"/college/courses/{cid}/structure",
                     json={"modules": [{"name": "Only", "topics": ["x"]}], "replace": True},
                     headers=auth).json()
    assert ws["modules"] == 1 and ws["topics_total"] == 1


def test_course_drive_link_is_stored_not_synced(client, auth):
    cid = client.post("/college/courses", json={"name": "DBMS"}, headers=auth).json()["id"]
    updated = client.patch(f"/college/courses/{cid}",
                           json={"drive_url": "https://drive.google.com/drive/folders/abc"},
                           headers=auth).json()
    assert updated["drive_url"].endswith("/abc")
    assert client.get(f"/college/courses/{cid}", headers=auth).json()["drive_url"].endswith("/abc")


def test_course_workspace_is_user_scoped(client, auth):
    other = client.post("/auth/register", json={"email": "cw@x.com", "password": "pass1234"}).json()
    client.cookies.clear()
    theirs = {"Authorization": f"Bearer {other['access_token']}"}
    cid = client.post("/college/courses", json={"name": "Mine"}, headers=auth).json()["id"]
    assert client.get(f"/college/courses/{cid}", headers=theirs).status_code == 404
    assert client.post(f"/college/courses/{cid}/modules", json={"name": "x"},
                       headers=theirs).status_code == 404


def test_low_attendance_raises_a_signal(client, auth):
    client.post("/college/courses", json={"name": "UI/UX Design", "attendance": 60}, headers=auth)
    signals = client.get("/spider-sense", headers=auth).json()
    assert any(s["kind"] == "attendance" for s in signals)


def test_exam_appears_in_college_and_planner(client, auth):
    client.post("/college/exams", json={"title": "DBMS CAT-2", "date": iso(days=2)}, headers=auth)
    college = client.get("/college", headers=auth).json()
    assert len(college["exams"]) == 1
    planner = client.get("/planner", headers=auth).json()
    assert any(i["kind"] == "exam" for d in planner["days"] for i in d["items"])


# ---------------------------------------------------------------- planner
def test_planner_merges_tasks_and_classes_and_schedules_undated(client, auth):
    c = client.post("/college/courses", json={"name": "Data Structures"}, headers=auth).json()
    today_dow = datetime.now().weekday()
    client.post("/college/classes", json={"course_id": c["id"], "day_of_week": today_dow,
                                          "start_time": "09:00", "end_time": "10:30"}, headers=auth)
    t = client.post("/tasks", json={"title": "Undated thing"}, headers=auth).json()

    p = client.get("/planner", headers=auth).json()
    assert any(i["kind"] == "class" for i in p["today"]["items"])
    assert any(u["id"] == t["id"] for u in p["unscheduled"])

    client.post(f"/planner/schedule/{t['id']}", json={"due_at": iso(hours=3)}, headers=auth)
    p2 = client.get("/planner", headers=auth).json()
    assert not any(u["id"] == t["id"] for u in p2["unscheduled"])


# ---------------------------------------------------------------- learning
def test_learning_session_moves_progress_and_recency(client, auth):
    t = client.post("/learning/topics", json={"name": "Trees & Graphs", "area": "DSA",
                                              "state": "needs_revision", "progress": 20}, headers=auth).json()
    r = client.post(f"/learning/topics/{t['id']}/sessions",
                    json={"minutes": 60, "note": "AVL rotations"}, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["topic_progress"] > 20

    over = client.get("/learning", headers=auth).json()
    topic = next(x for x in over["topics"] if x["id"] == t["id"])
    assert topic["minutes"] == 60 and topic["last_reviewed_at"] is not None
    assert over["week_minutes"] == 60


def test_scheduling_study_creates_a_planner_task(client, auth):
    t = client.post("/learning/topics", json={"name": "Transformers"}, headers=auth).json()
    r = client.post(f"/learning/topics/{t['id']}/schedule",
                    json={"due_at": iso(days=1), "minutes": 45}, headers=auth)
    assert r.status_code == 201
    tasks = client.get("/tasks", headers=auth).json()
    assert any(x["source"] == "learning" and "Transformers" in x["title"] for x in tasks)


def test_stale_revision_topic_raises_a_signal(client, auth):
    client.post("/learning/topics", json={"name": "Dynamic Programming", "state": "needs_revision"},
                headers=auth)
    signals = client.get("/spider-sense", headers=auth).json()
    assert any(s["kind"] == "revision" for s in signals)


# ---------------------------------------------------------------- projects
def test_project_phase_toggle_derives_completion(client, auth):
    p = client.post("/projects", json={"name": "EXPRESS OS", "stack": "Next.js"}, headers=auth).json()
    for name in ("Foundations", "Design System", "Backend Core", "Integrations"):
        p = client.post(f"/projects/{p['id']}/phases", json={"name": name}, headers=auth).json()
    assert p["completion"] == 0

    first = p["phases"][0]["id"]
    p = client.post(f"/projects/{p['id']}/phases/{first}/toggle", headers=auth).json()
    assert p["completion"] == 25
    assert p["phase"] == "Design System"       # headline advances to the next open phase


def test_project_task_materializes_and_mirrors_completion(client, auth):
    p = client.post("/projects", json={"name": "Portfolio"}, headers=auth).json()
    p = client.post(f"/projects/{p['id']}/tasks",
                    json={"title": "Write case study", "due_at": iso(days=2)}, headers=auth).json()
    tasks = client.get("/tasks", headers=auth).json()
    mirrored = next(t for t in tasks if t["source"] == "project")
    assert mirrored["title"] == "Write case study"

    ptid = p["tasks"][0]["id"]
    client.post(f"/projects/{p['id']}/tasks/{ptid}/toggle", headers=auth)
    tasks = client.get("/tasks", headers=auth).json()
    assert next(t for t in tasks if t["id"] == mirrored["id"])["status"] == "done"


# ---------------------------------------------------------------- career
def test_application_deadline_becomes_a_task_and_advances_status(client, auth):
    i = client.post("/career/internships", json={"company": "Stark Industries",
                                                 "role": "SWE Intern"}, headers=auth).json()
    a = client.post("/career/applications", json={"internship_id": i["id"], "stage": "oa",
                                                  "deadline": iso(days=1)}, headers=auth).json()
    tasks = client.get("/tasks", headers=auth).json()
    assert any(t["source"] == "career" and "Stark" in t["title"] for t in tasks)

    client.patch(f"/career/applications/{a['id']}", json={"stage": "interview"}, headers=auth)
    over = client.get("/career", headers=auth).json()
    assert over["internships"][0]["status"] == "Interviewing"
    assert over["pipeline"]["interview"] == 1
    assert any(s["kind"] == "career" for s in client.get("/spider-sense", headers=auth).json())


# ---------------------------------------------------------------- personal
def test_habit_toggle_derives_streak_both_ways(client, auth):
    rows = client.post("/personal/habits", json={"title": "Morning workout"}, headers=auth).json()
    hid = rows[0]["id"]
    assert rows[0]["streak"] == 0 and rows[0]["done_today"] is False

    rows = client.post(f"/personal/habits/{hid}/toggle", headers=auth).json()
    assert rows[0]["streak"] == 1 and rows[0]["done_today"] is True

    rows = client.post(f"/personal/habits/{hid}/toggle", headers=auth).json()
    assert rows[0]["streak"] == 0 and rows[0]["done_today"] is False   # un-ticking really rolls back


def test_note_anchors_to_a_project(client, auth):
    p = client.post("/projects", json={"name": "EXPRESS OS"}, headers=auth).json()
    n = client.post("/personal/notes", json={"title": "Decisions", "body": "Task queue is the spine.",
                                             "ref_type": "project", "ref_id": p["id"]}, headers=auth)
    assert n.status_code == 201
    over = client.get("/personal", headers=auth).json()
    assert over["notes"][0]["ref_label"] == "EXPRESS OS"
    assert client.get(f"/projects/{p['id']}", headers=auth).json()["note_count"] == 1


def test_note_rejects_an_unknown_ref_type(client, auth):
    r = client.post("/personal/notes", json={"body": "x", "ref_type": "nonsense"}, headers=auth)
    assert r.status_code == 422


# ---------------------------------------------------------------- finance
def test_budget_breach_raises_a_signal_and_matches_the_page(client, auth):
    client.post("/finance/budgets", json={"category": "Food", "monthly_limit": 1000}, headers=auth)
    client.post("/finance/entries", json={"amount": 900, "category": "Food"}, headers=auth)
    over = client.get("/finance", headers=auth).json()
    food = next(b for b in over["budgets"] if b["category"] == "Food")
    assert food["pct"] == 90 and food["state"] == "near"
    assert over["month_spent"] == 900

    client.post("/finance/entries", json={"amount": 200, "category": "Food"}, headers=auth)
    signals = client.get("/spider-sense", headers=auth).json()
    over2 = client.get("/finance", headers=auth).json()
    assert next(b for b in over2["budgets"] if b["category"] == "Food")["state"] == "over"
    assert any(s["kind"] == "budget" and "spent" in s["title"] for s in signals)


def test_income_does_not_count_against_a_budget(client, auth):
    client.post("/finance/budgets", json={"category": "Food", "monthly_limit": 1000}, headers=auth)
    client.post("/finance/entries", json={"amount": 5000, "category": "Food", "kind": "income"},
                headers=auth)
    over = client.get("/finance", headers=auth).json()
    assert next(b for b in over["budgets"] if b["category"] == "Food")["spent"] == 0
    assert over["month_income"] == 5000


# ---------------------------------------------------------------- goals
def test_goal_progress_is_derived_from_linked_work(client, auth):
    g = client.post("/goals", json={"title": "Ship EXPRESS OS"}, headers=auth).json()
    assert g["progress"] == 0 and g["progress_source"] == "manual"

    p = client.post("/projects", json={"name": "EXPRESS OS", "completion": 60}, headers=auth).json()
    g = client.post(f"/goals/{g['id']}/links",
                    json={"ref_type": "project", "ref_id": p["id"]}, headers=auth).json()
    assert g["progress"] == 60 and g["progress_source"] == "linked work"
    assert g["links"][0]["label"] == "EXPRESS OS"

    t = client.post("/tasks", json={"title": "Deploy"}, headers=auth).json()
    g = client.post(f"/goals/{g['id']}/links",
                    json={"ref_type": "task", "ref_id": t["id"]}, headers=auth).json()
    assert g["progress"] == 30            # (60 + 0) / 2
    client.post(f"/tasks/{t['id']}/complete", headers=auth)
    g = client.get("/goals", headers=auth).json()["goals"][0]
    assert g["progress"] == 80            # (60 + 100) / 2


def test_goal_cannot_link_to_another_users_row(client, auth):
    other = client.post("/auth/register", json={"email": "z@x.com", "password": "pass1234"}).json()
    other_auth = {"Authorization": f"Bearer {other['access_token']}"}
    theirs = client.post("/projects", json={"name": "Theirs"}, headers=other_auth).json()

    g = client.post("/goals", json={"title": "Mine"}, headers=auth).json()
    r = client.post(f"/goals/{g['id']}/links",
                    json={"ref_type": "project", "ref_id": theirs["id"]}, headers=auth)
    assert r.status_code == 404


# ---------------------------------------------------------------- memory
def test_memory_crud_and_counts(client, auth):
    m = client.post("/memory", json={"text": "I prefer DSA at night",
                                     "category": "Preference"}, headers=auth).json()
    assert m["source"] == "manual"

    client.patch(f"/memory/{m['id']}", json={"pinned": True, "category": "Note"}, headers=auth)
    over = client.get("/memory", headers=auth).json()
    assert over["total"] == 1 and over["pinned"] == 1 and over["counts"]["Note"] == 1

    filtered = client.get("/memory?q=nothing-matches", headers=auth).json()
    assert filtered["memories"] == [] and filtered["total"] == 1   # counts describe the whole store

    client.delete(f"/memory/{m['id']}", headers=auth)
    assert client.get("/memory", headers=auth).json()["total"] == 0


# ---------------------------------------------------------------- integrations
def test_unconfigured_provider_cannot_be_connected(client, auth):
    rows = client.get("/integrations", headers=auth).json()
    github = next(i for i in rows["integrations"] if i["provider"] == "github")
    assert github["status"] == "unconfigured" and github["connectable"] is False
    assert "GITHUB_CLIENT_ID" in github["requires"]

    r = client.post("/integrations/github/connect", json={}, headers=auth)
    assert r.status_code == 409


# ---------------------------------------------------------------- progress
def test_progress_report_counts_every_module(client, auth):
    client.post("/tasks", json={"title": "One"}, headers=auth)
    client.post("/college/courses", json={"name": "OS", "attendance": 70}, headers=auth)
    client.post("/learning/topics", json={"name": "Pandas", "progress": 90, "state": "strong"}, headers=auth)
    client.post("/projects", json={"name": "EXPRESS", "completion": 40}, headers=auth)
    client.post("/goals", json={"title": "Ship it", "progress": 20}, headers=auth)
    client.post("/finance/entries", json={"amount": 100, "category": "Food"}, headers=auth)

    r = client.get("/progress/report", headers=auth).json()
    assert r["tasks"]["total"] == 1 and len(r["tasks"]["series"]) == 14
    assert r["college"]["at_risk"][0]["name"] == "OS"
    assert r["learning"]["strong"] == 1
    assert r["projects"]["avg_completion"] == 40
    assert r["goals"]["total"] == 1
    assert r["finance"]["month_spent"] == 100
    assert r["signals"]["active"] >= 1


def test_signals_expose_the_module_they_point_at(client, auth):
    """The Home page routes a signal to its module, so `module` must survive
    serialization — it is easy to add on the model and forget on the schema."""
    client.post("/college/courses", json={"name": "UI/UX Design", "attendance": 60}, headers=auth)
    client.post("/finance/budgets", json={"category": "Books", "monthly_limit": 100}, headers=auth)
    client.post("/finance/entries", json={"amount": 200, "category": "Books"}, headers=auth)

    signals = client.get("/spider-sense", headers=auth).json()
    assert signals, "expected at least one signal"
    assert all("module" in s for s in signals)
    assert {s["module"] for s in signals} >= {"college", "finance"}


def test_planner_renders_times_on_the_users_clock_not_utc(client, auth, monkeypatch):
    """Storage is UTC; the day window is computed in the local zone. Formatting a
    stored instant directly renders the wrong hour for any non-UTC user — an item
    at 00:00 local displayed as 18:30. Times must be converted before display.

    Deliberately built from the *current* local day rather than a fixed calendar
    instant, so the test asserts the conversion rather than today's date.
    """
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings
    from app.services import timeutils

    monkeypatch.setattr(settings, "LOCAL_TZ", "Asia/Kolkata")   # UTC+5:30

    # The pure conversion: 18:30 UTC is midnight the next day in IST.
    fixed = datetime(2026, 8, 26, 18, 30, tzinfo=timezone.utc)
    assert timeutils.local_hhmm(fixed) == "00:00"
    assert fixed.strftime("%H:%M") == "18:30", "this is the old, wrong output"

    # And the endpoint agrees, for an instant guaranteed to sit in today's
    # local window whatever the real date is.
    instant = timeutils.start_of_local_day(0) + timedelta(hours=10)
    expected = timeutils.local_hhmm(instant)
    assert expected == "10:00", f"local day should start at midnight IST, got {expected}"

    r = client.post("/tasks", json={"title": "Local clock task",
                                    "due_at": instant.isoformat()}, headers=auth)
    assert r.status_code == 201
    planner = client.get("/planner", headers=auth).json()
    rendered = [i["time"] for d in planner["days"] for i in d["items"]
                if i["title"] == "Local clock task"]
    assert rendered, "the task did not appear in the planner window"
    assert rendered[0] == expected, (
        f"planner rendered {rendered[0]}, expected {expected} "
        f"(UTC would have been {instant.strftime('%H:%M')})")

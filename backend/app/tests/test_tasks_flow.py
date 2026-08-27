from datetime import datetime, timezone, timedelta


def test_task_crud_and_reschedule(client, auth):
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post("/tasks", json={"title": "Wash shoes", "due_at": due}, headers=auth)
    assert r.status_code == 201
    tid = r.json()["id"]

    # reschedule increments postpone_count and propagates
    new_due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r2 = client.post(f"/tasks/{tid}/reschedule", json={"due_at": new_due}, headers=auth)
    assert r2.status_code == 200 and r2.json()["postpone_count"] == 1

    # complete
    r3 = client.post(f"/tasks/{tid}/complete", headers=auth)
    assert r3.status_code == 200 and r3.json()["status"] == "done"


def test_assignment_materializes_task(client, auth):
    due = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
    r = client.post("/assignments", json={"title": "DBMS Assignment", "due_at": due}, headers=auth)
    assert r.status_code == 201
    tasks = client.get("/tasks", headers=auth).json()
    assert any(t["source"] == "assignment" and t["title"] == "DBMS Assignment" for t in tasks)


def test_user_isolation(client):
    # two users cannot see each other's tasks
    a = client.post("/auth/register", json={"email": "u1@x.com", "password": "pass1234"}).json()["access_token"]
    b = client.post("/auth/register", json={"email": "u2@x.com", "password": "pass1234"}).json()["access_token"]
    client.post("/tasks", json={"title": "secret"}, headers={"Authorization": f"Bearer {a}"})
    b_tasks = client.get("/tasks", headers={"Authorization": f"Bearer {b}"}).json()
    assert b_tasks == []

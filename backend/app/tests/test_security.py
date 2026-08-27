"""Authentication, authorization and ownership.

These are the tests that must never be allowed to go red: they are the
difference between a multi-user app and a data leak.
"""
import pytest

PROTECTED = [
    ("GET", "/home"), ("GET", "/tasks"), ("GET", "/planner"), ("GET", "/college"),
    ("GET", "/learning"), ("GET", "/projects"), ("GET", "/career"), ("GET", "/goals"),
    ("GET", "/personal"), ("GET", "/finance"), ("GET", "/memory"),
    ("GET", "/progress/report"), ("GET", "/integrations"), ("GET", "/spider-sense"),
    ("GET", "/auth/me"), ("POST", "/jocasta/message"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_protected_route_rejects_anonymous(client, method, path):
    r = client.request(method, path, json={} if method == "POST" else None)
    assert r.status_code == 401, f"{method} {path} returned {r.status_code}"


@pytest.mark.parametrize("token", ["", "garbage", "Bearer.nope", "a.b.c"])
def test_malformed_tokens_are_rejected(client, token):
    r = client.get("/tasks", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token(client):
    """The two token types are deliberately distinguishable; using the long-lived
    one as a bearer would defeat the short access-token lifetime."""
    from app.core.security import create_refresh_token
    refresh = create_refresh_token("00000000-0000-0000-0000-000000000000")
    r = client.get("/tasks", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


def test_expired_access_token_is_rejected(client, auth):
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core.config import settings
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "type": "access",
         "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    r = client.get("/tasks", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_token_signed_with_another_key_is_rejected(client):
    from datetime import datetime, timedelta, timezone
    import jwt
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "type": "access",
         "iat": now, "exp": now + timedelta(hours=1)},
        "not-the-real-secret", algorithm="HS256")
    r = client.get("/tasks", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_weak_password_is_rejected(client):
    r = client.post("/auth/register", json={"email": "weak@x.com", "password": "short"})
    assert r.status_code == 422


def test_duplicate_registration_conflicts(client):
    body = {"email": "dupe@x.com", "password": "pass1234"}
    assert client.post("/auth/register", json=body).status_code == 200
    assert client.post("/auth/register", json=body).status_code == 409


def test_logout_clears_the_refresh_cookie(client):
    """The refresh cookie is httpOnly, so only the server can remove it. If this
    regresses, a logged-out browser can still mint access tokens."""
    r = client.post("/auth/register", json={"email": "bye@x.com", "password": "pass1234"})
    assert r.status_code == 200
    assert client.cookies.get("express_refresh")          # session established

    assert client.post("/auth/refresh").status_code == 200  # redeemable before logout
    assert client.post("/auth/logout").status_code == 204
    assert not client.cookies.get("express_refresh")        # cookie actually gone
    assert client.post("/auth/refresh").status_code == 401   # and no longer redeemable


# ---------------------------------------------------------------- ownership
def _register(client, email):
    tok = client.post("/auth/register", json={"email": email, "password": "pass1234"}).json()
    client.cookies.clear()      # don't let one user's refresh cookie leak into the next
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_one_user_cannot_read_or_mutate_anothers_rows(client):
    a = _register(client, "owner@x.com")
    b = _register(client, "intruder@x.com")

    task = client.post("/tasks", json={"title": "A's private task"}, headers=a).json()
    project = client.post("/projects", json={"name": "A's project"}, headers=a).json()
    note = client.post("/personal/notes", json={"body": "A's note"}, headers=a).json()
    memory = client.post("/memory", json={"text": "A's memory"}, headers=a).json()
    goal = client.post("/goals", json={"title": "A's goal"}, headers=a).json()

    # B sees nothing of A's
    assert client.get("/tasks", headers=b).json() == []
    assert client.get("/projects", headers=b).json()["projects"] == []
    assert client.get("/personal", headers=b).json()["notes"] == []
    assert client.get("/memory", headers=b).json()["total"] == 0
    assert client.get("/goals", headers=b).json()["goals"] == []

    # B cannot mutate A's rows by guessing ids
    assert client.post(f"/tasks/{task['id']}/complete", headers=b).status_code == 404
    assert client.patch(f"/projects/{project['id']}", json={"name": "hijacked"}, headers=b).status_code == 404
    assert client.patch(f"/personal/notes/{note['id']}", json={"body": "hijacked"}, headers=b).status_code == 404
    assert client.patch(f"/memory/{memory['id']}", json={"text": "hijacked"}, headers=b).status_code == 404
    assert client.delete(f"/goals/{goal['id']}", headers=b).status_code == 404

    # ...and A's data is untouched
    assert client.get("/tasks", headers=a).json()[0]["status"] == "open"
    assert client.get("/projects", headers=a).json()["projects"][0]["name"] == "A's project"
    assert client.get("/memory", headers=a).json()["memories"][0]["text"] == "A's memory"


def test_deleting_another_users_row_does_not_silently_succeed(client):
    a = _register(client, "keeper@x.com")
    b = _register(client, "deleter@x.com")
    course = client.post("/college/courses", json={"name": "A's course"}, headers=a).json()

    assert client.delete(f"/college/courses/{course['id']}", headers=b).status_code == 404
    assert len(client.get("/college", headers=a).json()["courses"]) == 1


def test_jocasta_tools_cannot_reach_another_users_rows(client):
    a = _register(client, "ja@x.com")
    b = _register(client, "jb@x.com")
    client.post("/learning/topics", json={"name": "Quantum Field Theory"}, headers=a)

    out = client.post("/jocasta/message",
                      json={"text": "studied quantum field theory for 30 minutes"},
                      headers=b).json()
    call = next(c for c in out["calls"] if c["tool"] == "log_study")
    assert not call["ok"], "JOCasta matched a topic belonging to a different user"
    assert client.get("/learning", headers=a).json()["total_minutes"] == 0

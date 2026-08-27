def test_register_login_me(client):
    r = client.post("/auth/register", json={"email": "a@b.c", "password": "pw123456", "name": "Pooji"})
    assert r.status_code == 200
    r2 = client.post("/auth/login", json={"email": "a@b.c", "password": "pw123456"})
    assert r2.status_code == 200
    token = r2.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "a@b.c"


def test_protected_requires_auth(client):
    assert client.get("/tasks").status_code == 401


def test_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "x@y.z", "password": "rightpass"})
    assert client.post("/auth/login", json={"email": "x@y.z", "password": "wrongpass"}).status_code == 401

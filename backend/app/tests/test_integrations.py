"""Integrations: honest state, real OAuth mechanics, and tokens that stay server-side.

None of these need live provider credentials — they exercise the parts EXPRESS
is responsible for.
"""
import pytest

from app.core.config import settings
from app.integrations import crypto, oauth
from app.integrations.providers import PROVIDERS, get as get_provider
from app.models import Integration, User


# ---------------------------------------------------------------- honesty
def test_unconfigured_providers_report_honestly_and_refuse_to_connect(client, auth):
    body = client.get("/integrations", headers=auth).json()
    assert body["integrations"], "expected a provider registry"
    for row in body["integrations"]:
        # Nothing is configured in the test environment.
        assert row["status"] == "unconfigured"
        assert row["connectable"] is False
        assert row["requires"], "an unavailable provider must say what is missing"
        assert row["last_sync_at"] is None
    assert body["connected"] == 0


def test_starting_a_flow_without_credentials_is_refused(client, auth):
    for provider in PROVIDERS:
        r = client.post(f"/integrations/{provider}/authorize", headers=auth)
        assert r.status_code == 409, f"{provider} offered a flow it cannot complete"
        assert "not configured" in r.json()["detail"].lower()


def test_unknown_provider_is_404(client, auth):
    assert client.post("/integrations/nonsense/authorize", headers=auth).status_code == 404


# ---------------------------------------------------------------- crypto
def test_tokens_round_trip_and_are_not_stored_in_the_clear():
    secret = "ya29.a0AfH6SMB-super-secret-access-token"
    sealed = crypto.encrypt(secret)
    assert sealed and secret not in sealed, "the plaintext token leaked into storage"
    assert crypto.decrypt(sealed) == secret


def test_unreadable_token_degrades_instead_of_raising(monkeypatch):
    """If SECRET_KEY changes, old tokens must read as absent, not crash a page."""
    sealed = crypto.encrypt("token")
    monkeypatch.setattr(settings, "SECRET_KEY", "a-completely-different-secret-key-value")
    assert crypto.decrypt(sealed) is None


def test_empty_values_are_handled():
    assert crypto.encrypt(None) is None
    assert crypto.encrypt("") is None
    assert crypto.decrypt(None) is None
    assert crypto.decrypt("not-valid-ciphertext") is None


# ---------------------------------------------------------------- oauth mechanics
@pytest.fixture()
def google(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    return get_provider("calendar")


def test_authorize_url_carries_pkce_and_state(google):
    url = oauth.build_authorize_url(google, "11111111-1111-1111-1111-111111111111")
    for required in ("code_challenge=", "code_challenge_method=S256", "state=",
                     "response_type=code", "client_id=test-client-id"):
        assert required in url, f"authorize URL missing {required}"
    # The verifier itself must never appear in the URL.
    assert "code_verifier" not in url


def test_state_is_bound_to_its_provider_and_expires(google):
    url = oauth.build_authorize_url(google, "11111111-1111-1111-1111-111111111111")
    state = url.split("state=")[1].split("&")[0]

    payload = oauth.verify_state(state, "calendar")
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["v"], "the PKCE verifier must travel inside the signed state"

    with pytest.raises(ValueError):
        oauth.verify_state(state, "github")        # wrong provider
    with pytest.raises(ValueError):
        oauth.verify_state(state + "tamper", "calendar")
    with pytest.raises(ValueError):
        oauth.verify_state("not-a-token", "calendar")


def test_callback_rejects_a_forged_state(client, google):
    r = client.get("/integrations/calendar/callback",
                   params={"code": "abc", "state": "forged"}, follow_redirects=False)
    # It redirects back to the UI with an error rather than connecting anything.
    assert r.status_code in (302, 307)
    assert "error=" in r.headers["location"]


def test_callback_reports_provider_errors_without_connecting(client, google, db_session):
    r = client.get("/integrations/calendar/callback",
                   params={"error": "access_denied"}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    assert db_session.query(Integration).count() == 0


def test_callback_without_code_does_not_connect(client, google, db_session):
    r = client.get("/integrations/calendar/callback", follow_redirects=False)
    assert "error=" in r.headers["location"]
    assert db_session.query(Integration).count() == 0


# ---------------------------------------------------------------- no token leakage
def test_no_endpoint_ever_returns_a_token(client, auth, db_session):
    """The strongest guarantee here: tokens exist server-side only."""
    user = db_session.query(User).first()
    db_session.add(Integration(
        user_id=user.id, provider="calendar", status="connected",
        encrypted_token=crypto.encrypt("SECRET-ACCESS-TOKEN"),
        encrypted_refresh=crypto.encrypt("SECRET-REFRESH-TOKEN")))
    db_session.commit()

    body = client.get("/integrations", headers=auth).text
    for leaked in ("SECRET-ACCESS-TOKEN", "SECRET-REFRESH-TOKEN",
                   "encrypted_token", "encrypted_refresh"):
        assert leaked not in body, f"{leaked} was exposed to the client"


def test_refresh_without_a_stored_refresh_token_is_refused(client, auth, db_session):
    user = db_session.query(User).first()
    db_session.add(Integration(user_id=user.id, provider="github", status="connected",
                               encrypted_token=crypto.encrypt("access-only")))
    db_session.commit()
    r = client.post("/integrations/github/refresh", headers=auth)
    assert r.status_code == 409
    assert "reconnect" in r.json()["detail"].lower()


def test_disconnect_destroys_the_stored_tokens(client, auth, db_session):
    user = db_session.query(User).first()
    db_session.add(Integration(user_id=user.id, provider="calendar", status="connected",
                               encrypted_token=crypto.encrypt("tok")))
    db_session.commit()

    assert client.post("/integrations/calendar/disconnect", headers=auth).status_code == 204
    assert db_session.query(Integration).filter(
        Integration.user_id == user.id, Integration.provider == "calendar").first() is None


def test_one_user_cannot_disconnect_anothers_integration(client, db_session):
    a = client.post("/auth/register", json={"email": "ia@x.com", "password": "pass1234"}).json()
    client.cookies.clear()
    b = client.post("/auth/register", json={"email": "ib@x.com", "password": "pass1234"}).json()
    client.cookies.clear()
    owner = db_session.query(User).filter(User.email == "ia@x.com").first()
    db_session.add(Integration(user_id=owner.id, provider="calendar", status="connected",
                               encrypted_token=crypto.encrypt("tok")))
    db_session.commit()

    client.post("/integrations/calendar/disconnect",
                headers={"Authorization": f"Bearer {b['access_token']}"})
    assert db_session.query(Integration).filter(Integration.user_id == owner.id).first() is not None

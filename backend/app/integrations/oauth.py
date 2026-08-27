"""OAuth 2.0 authorization-code flow.

What this module guarantees:

* **CSRF protection.** The `state` parameter is a signed, short-lived token
  bound to the user and provider. A callback whose state doesn't verify is
  rejected — without this, an attacker can complete a flow into someone else's
  account.
* **PKCE.** A code verifier is generated per attempt and its challenge sent on
  the authorize request, so an intercepted authorization code is useless on its
  own. The verifier travels inside the signed state, never in a cookie.
* **Tokens never reach the browser.** The exchange happens server-side and the
  result is encrypted before it touches the database. No endpoint returns a
  token, and no response model contains one.
* **Honest state.** A provider without server-side credentials cannot start a
  flow at all, and a failed exchange records the error rather than reporting a
  connection that does not exist.
"""
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings
from app.core.logging import log
from app.integrations.providers import Provider

logger = logging.getLogger("express.integrations")

STATE_TTL_SECONDS = 600
_AUDIENCE = "oauth-state"
EXCHANGE_TIMEOUT = 15.0


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(provider: Provider, user_id) -> str:
    """The URL to send the user to. Raises if the provider isn't configured."""
    if not provider.configured:
        raise ValueError(f"{provider.label} is not configured on the server "
                         f"({provider.missing} missing).")

    verifier, challenge = _pkce_pair()
    now = datetime.now(timezone.utc)
    state = jwt.encode(
        {"sub": str(user_id), "provider": provider.name, "aud": _AUDIENCE,
         "v": verifier, "nonce": secrets.token_urlsafe(8),
         "iat": now, "exp": now + timedelta(seconds=STATE_TTL_SECONDS)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri(),
        "response_type": "code",
        "scope": " ".join(provider.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **provider.extra_authorize,
    }
    return f"{provider.authorize_url}?{urlencode(params)}"


def verify_state(state: str, provider_name: str) -> dict:
    """Returns the state payload, or raises. Binds the callback to one user."""
    try:
        payload = jwt.decode(state, settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM], audience=_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise ValueError("That authorization link expired. Start the connection again.")
    except Exception:
        raise ValueError("Invalid authorization state.")
    if payload.get("provider") != provider_name:
        raise ValueError("Invalid authorization state.")
    return payload


def exchange_code(provider: Provider, code: str, verifier: str) -> dict:
    """Swap an authorization code for tokens. Returns the raw provider payload.

    Never logs the response body — it contains the tokens.
    """
    data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": provider.redirect_uri(),
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    resp = httpx.post(provider.token_url, data=data,
                      headers={"Accept": "application/json"}, timeout=EXCHANGE_TIMEOUT)
    if resp.status_code >= 400:
        log(logger, logging.WARNING, "token exchange rejected",
            provider=provider.name, status=resp.status_code)
        raise ValueError(f"{provider.label} rejected the authorization "
                         f"(HTTP {resp.status_code}).")
    payload = resp.json()
    if "error" in payload:
        log(logger, logging.WARNING, "token exchange error",
            provider=provider.name, error=payload.get("error"))
        raise ValueError(f"{provider.label} returned: {payload.get('error')}")
    if not payload.get("access_token"):
        raise ValueError(f"{provider.label} did not return an access token.")
    return payload


def refresh_token(provider: Provider, refresh: str) -> dict:
    """Exchange a refresh token for a new access token."""
    resp = httpx.post(provider.token_url, data={
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }, headers={"Accept": "application/json"}, timeout=EXCHANGE_TIMEOUT)
    if resp.status_code >= 400:
        raise ValueError(f"{provider.label} refused to refresh the token "
                         f"(HTTP {resp.status_code}).")
    payload = resp.json()
    if "error" in payload or not payload.get("access_token"):
        raise ValueError(f"{provider.label} refresh failed.")
    return payload


def expiry_from(payload: dict) -> datetime | None:
    seconds = payload.get("expires_in")
    if not seconds:
        return None                     # GitHub tokens do not expire by default
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
    except (TypeError, ValueError):
        return None

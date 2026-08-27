"""Integrations: the connection registry and the OAuth flow.

Nothing here fakes a connection. A provider is `unconfigured` until the server
holds its client credentials, `disconnected` until a flow completes, and
`connected` only once a token exchange actually succeeded. A failed exchange
records the error and leaves the status honest.

Tokens never leave the server: no response model contains one, and the only
code that reads them decrypts on demand.
"""
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import log
from app.integrations import crypto, oauth
from app.integrations.providers import PROVIDERS, get as get_provider
from app.models import Integration, User
from app.schemas.integrations import IntegrationConnect, IntegrationOut

logger = logging.getLogger("express.integrations")
router = APIRouter(prefix="/integrations", tags=["integrations"])


def _row(db, user_id, provider_name) -> Integration | None:
    return (db.query(Integration)
            .filter(Integration.user_id == user_id,
                    Integration.provider == provider_name).first())


def _status(provider, row: Integration | None) -> str:
    if not provider.configured:
        return "unconfigured"
    if row is None:
        return "disconnected"
    if row.last_error:
        return "error"
    if row.encrypted_token:
        return "connected"
    return row.status or "disconnected"


def _serialize(provider, row: Integration | None) -> dict:
    status = _status(provider, row)
    expires = row.token_expires_at if row else None
    return {
        "provider": provider.name, "label": provider.label, "icon": provider.icon,
        "blurb": provider.blurb, "scopes": " ".join(provider.scopes),
        "id": str(row.id) if row else None,
        "status": status,
        "connectable": provider.configured,
        "account_label": (row.account_label if row else "") or "",
        "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
        "last_error": (row.last_error if row else "") or "",
        "token_expires_at": expires.isoformat() if expires else None,
        "token_expired": bool(expires and expires < datetime.now(timezone.utc)),
        "requires": None if provider.configured
                    else f"{provider.missing} not set on the server",
        "redirect_uri": provider.redirect_uri() if provider.configured else None,
    }


@router.get("")
def list_integrations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = {r.provider: r for r in
            db.query(Integration).filter(Integration.user_id == user.id).all()}
    out = [_serialize(p, rows.get(name)) for name, p in PROVIDERS.items()]
    return {
        "integrations": out,
        "connected": len([o for o in out if o["status"] == "connected"]),
        "note": ("Connecting opens the provider's own consent screen. Tokens are "
                 "encrypted before storage and are never sent to this browser. A "
                 "provider stays unavailable until its credentials are configured "
                 "on the server."),
    }


@router.post("/{provider_name}/authorize")
def authorize(provider_name: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Start a connection. Returns the provider's consent URL to redirect to."""
    provider = get_provider(provider_name)
    if not provider:
        raise HTTPException(404, "Unknown provider")
    try:
        url = oauth.build_authorize_url(provider, user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    row = _row(db, user.id, provider_name)
    if row is None:
        row = Integration(user_id=user.id, provider=provider_name)
        db.add(row)
    row.status = "pending"
    row.last_error = ""
    row.scopes = " ".join(provider.scopes)
    db.commit()
    log(logger, logging.INFO, "oauth started", provider=provider_name, user_id=str(user.id))
    return {"authorize_url": url, "provider": provider_name,
            "redirect_uri": provider.redirect_uri()}


@router.get("/{provider_name}/callback")
def callback(provider_name: str, code: str | None = None, state: str | None = None,
             error: str | None = None, db: Session = Depends(get_db)):
    """Handle the provider's redirect.

    Deliberately unauthenticated in the usual sense: a redirect from Google or
    GitHub carries no Authorization header. Identity comes from the signed
    `state`, which is bound to the user who started the flow — that binding is
    the CSRF defence.
    """
    frontend = f"{settings.FRONTEND_ORIGIN.rstrip('/')}/integrations"
    provider = get_provider(provider_name)
    if not provider:
        return RedirectResponse(f"{frontend}?{urlencode({'error': 'Unknown provider'})}")

    def fail(message: str, row: Integration | None = None):
        if row is not None:
            row.last_error = message[:240]
            row.status = "error"
            db.commit()
        log(logger, logging.WARNING, "oauth failed",
            provider=provider_name, reason=message[:120])
        return RedirectResponse(f"{frontend}?{urlencode({'error': message})}")

    if error:
        return fail(f"{provider.label} reported: {error}")
    if not code or not state:
        return fail("The provider redirect was missing its code or state.")

    try:
        payload = oauth.verify_state(state, provider_name)
    except ValueError as exc:
        return fail(str(exc))

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        return fail("That authorization no longer matches an account.")

    row = _row(db, user.id, provider_name)
    if row is None:
        row = Integration(user_id=user.id, provider=provider_name)
        db.add(row)

    try:
        tokens = oauth.exchange_code(provider, code, payload["v"])
    except ValueError as exc:
        return fail(str(exc), row)
    except Exception:
        logger.exception("token exchange crashed")
        return fail(f"Could not reach {provider.label} to complete the connection.", row)

    row.encrypted_token = crypto.encrypt(tokens.get("access_token"))
    row.encrypted_refresh = crypto.encrypt(tokens.get("refresh_token"))
    row.token_expires_at = oauth.expiry_from(tokens)
    row.scopes = tokens.get("scope") or " ".join(provider.scopes)
    row.status = "connected"
    row.last_error = ""
    row.last_sync_at = None      # connected, but nothing has synced yet
    db.commit()
    log(logger, logging.INFO, "oauth connected",
        provider=provider_name, user_id=str(user.id),
        has_refresh=bool(tokens.get("refresh_token")))
    return RedirectResponse(f"{frontend}?{urlencode({'connected': provider.label})}")


@router.post("/{provider_name}/refresh")
def refresh(provider_name: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Renew an access token using the stored refresh token."""
    provider = get_provider(provider_name)
    if not provider:
        raise HTTPException(404, "Unknown provider")
    row = _row(db, user.id, provider_name)
    if not row or not row.encrypted_refresh:
        raise HTTPException(409, f"{provider.label} has no refresh token stored. "
                                 "Reconnect to obtain one.")
    stored = crypto.decrypt(row.encrypted_refresh)
    if not stored:
        row.last_error = "Stored credentials could not be read. Reconnect to fix this."
        row.status = "error"
        db.commit()
        raise HTTPException(409, row.last_error)

    try:
        tokens = oauth.refresh_token(provider, stored)
    except Exception as exc:
        row.last_error = str(exc)[:240]
        row.status = "error"
        db.commit()
        raise HTTPException(502, row.last_error)

    row.encrypted_token = crypto.encrypt(tokens.get("access_token"))
    if tokens.get("refresh_token"):
        row.encrypted_refresh = crypto.encrypt(tokens["refresh_token"])
    row.token_expires_at = oauth.expiry_from(tokens)
    row.status = "connected"
    row.last_error = ""
    db.commit()
    return _serialize(provider, row)


@router.post("/{provider_name}/disconnect", status_code=204)
def disconnect(provider_name: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Forget the connection and destroy the stored tokens."""
    row = _row(db, user.id, provider_name)
    if row:
        db.delete(row)
        db.commit()
        log(logger, logging.INFO, "integration disconnected",
            provider=provider_name, user_id=str(user.id))
    return


# Kept for compatibility with the pre-OAuth UI: recording intent without
# credentials is no longer possible, so this now redirects callers to the real flow.
@router.post("/{provider_name}/connect")
def connect(provider_name: str, body: IntegrationConnect,
            db: Session = Depends(get_db), user=Depends(get_current_user)):
    return authorize(provider_name, db, user)

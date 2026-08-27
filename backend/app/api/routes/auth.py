import logging

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (hash_password, verify_password, create_access_token,
                               create_refresh_token, decode_token)
from app.core.config import settings
from app.models import User
from app.schemas.auth import RegisterIn, LoginIn, TokenOut, UserOut
from app.api.deps import get_current_user

from app.core.logging import log

logger = logging.getLogger("express.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "express_refresh"
# The cookie is scoped to /auth so it is never sent to ordinary API routes —
# it can only be redeemed at the refresh endpoint.
REFRESH_PATH = "/auth"


def _set_refresh(resp: Response, sub: str):
    resp.set_cookie(
        REFRESH_COOKIE, create_refresh_token(sub), httponly=True, samesite="lax",
        secure=settings.secure_cookies,
        max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path=REFRESH_PATH,
    )


def _issue(resp: Response, user: User) -> TokenOut:
    _set_refresh(resp, str(user.id))
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, resp: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password), name=body.name)
    db.add(user); db.commit(); db.refresh(user)
    return _issue(resp, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    """JSON login used by the web app."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        # Same message either way — distinguishing them would confirm which
        # addresses are registered.
        log(logger, logging.WARNING, "login rejected", email=body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    log(logger, logging.INFO, "login", user_id=str(user.id))
    return _issue(resp, user)


@router.post("/token", response_model=TokenOut)
def token(resp: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form login — powers the Swagger 'Authorize' button and standard clients."""
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _issue(resp, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request):
    tok = request.cookies.get(REFRESH_COOKIE)
    if not tok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        payload = decode_token(tok)
        assert payload.get("type") == "refresh"
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return TokenOut(access_token=create_access_token(payload["sub"]))


@router.post("/logout", status_code=204)
def logout():
    """Clear the refresh cookie.

    The frontend can drop its in-memory access token on its own, but the
    refresh cookie is httpOnly — only the server can remove it. Without this the
    session outlives "log out": anyone with the browser could still redeem
    /auth/refresh for a fresh access token.

    Deliberately unauthenticated: logging out must work even once the access
    token has already expired.

    The Set-Cookie header has to go on the response that is actually returned —
    building it here rather than mutating an injected one is what makes that
    unambiguous.
    """
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH,
                       httponly=True, samesite="lax", secure=settings.secure_cookies)
    return resp


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

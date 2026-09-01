"""First-run bootstrap.

EXPRESS deliberately seeds **no content**. A new account starts empty and the
user builds their own courses, goals, projects and plan — demo rows would be
indistinguishable from real ones the moment they appeared on screen, and every
derived number (attendance, progress, XP) would then be describing fiction.

Only the sign-in account is created, so there is something to log in with.
Every module handles the empty case explicitly.
"""
import logging

from app.core.config import settings
from app.core.logging import log
from app.core.security import hash_password
from app.models import User

logger = logging.getLogger("express.seed")


def seed(db) -> User | None:
    """Create the configured account if the database has no users."""
    if not settings.DEMO_EMAIL:
        log(logger, logging.INFO, "no DEMO_EMAIL set; skipping account creation")
        return None

    user = User(email=settings.DEMO_EMAIL, name="Pooji",
                hashed_password=hash_password(settings.DEMO_PASSWORD))
    db.add(user)
    db.commit()
    db.refresh(user)
    log(logger, logging.INFO, "created sign-in account (no content seeded)",
        email=settings.DEMO_EMAIL)
    return user


def backfill(db, user=None) -> None:
    """Intentionally does nothing.

    Earlier revisions filled empty modules with sample rows on every boot. That
    made a fresh install look populated and quietly re-created demo content
    after a user deleted it. Empty states are the correct answer instead.
    """
    return None

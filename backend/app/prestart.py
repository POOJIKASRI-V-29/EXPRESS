"""Runs before the server starts: wait for the database, migrate, seed if empty.

Migration strategy
------------------
Alembic is the source of truth. Three cases are handled:

  1. Empty database          -> `upgrade head` builds everything.
  2. Tables but no Alembic   -> a database created by the original pre-Alembic
                                bootstrap. Its tables and columns already match
                                revision 0001, so it is *stamped* at 0001 (no
                                re-creation, no data loss) and later revisions
                                are then applied normally.
  3. Already under Alembic   -> `upgrade head`.

In development only, an additive column sync runs afterwards as a safety net so
a model edit doesn't require a hand-written migration mid-session. It only ever
ADDs columns, and it logs loudly when it does anything — if it fires, a real
migration is missing.
"""
import logging
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.core.logging import configure as configure_logging, log
from app.core import schema_sync
import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.models import User
from app import seed as seed_mod

configure_logging()
logger = logging.getLogger("express.prestart")

BASELINE_REVISION = "8f892c67f481"


def wait_for_db(retries: int = 30) -> None:
    for i in range(retries):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception:
            log(logger, logging.INFO, "waiting for database", attempt=i + 1, of=retries)
            time.sleep(1)
    raise RuntimeError("Database not reachable")


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def migrate() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    cfg = _alembic_config()

    if "alembic_version" not in tables and tables:
        # Pre-Alembic database: adopt it rather than rebuild it.
        log(logger, logging.WARNING, "adopting pre-Alembic database",
            tables=len(tables), stamped_at=BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")
    log(logger, logging.INFO, "migrations applied", target="head")


def main() -> None:
    wait_for_db()
    migrate()

    if settings.is_development:
        added = schema_sync.sync(engine, Base.metadata)
        if added:
            log(logger, logging.WARNING,
                "dev schema sync added columns — a migration is missing for these",
                columns=added)

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            log(logger, logging.INFO, "seeding demo data")
            seed_mod.seed(db)
        else:
            seed_mod.backfill(db)
    finally:
        db.close()
    log(logger, logging.INFO, "prestart complete", env=settings.ENV)


if __name__ == "__main__":
    main()

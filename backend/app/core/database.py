import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, CHAR, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# SQLite (tests) rejects pool sizing arguments, so they are applied only to
# a real server-backed pool.
_pool_kwargs = {} if settings.DATABASE_URL.startswith("sqlite") else {
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_recycle": settings.DB_POOL_RECYCLE,
}
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True,
                       connect_args=connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class GUID(TypeDecorator):
    """Portable UUID: native uuid on Postgres, CHAR(36) elsewhere (tests use sqlite)."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class UTCDateTime(TypeDecorator):
    """A timezone-aware datetime that behaves identically on every backend.

    Postgres returns aware datetimes for `TIMESTAMPTZ`; SQLite (used by the
    tests) returns naive ones. Anything comparing a stored datetime to
    `now()` then raises "can't compare offset-naive and offset-aware datetimes"
    on SQLite while working fine in production — a bug class that only shows up
    where it is least useful.

    Storage is always UTC, so a naive value read back is UTC that lost its
    label. This reattaches it on the way out and normalises to UTC on the way
    in, making the two backends indistinguishable to application code.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_db():
    """Request-scoped session.

    Rolls back on any exception so a failed request can never leave partially
    applied writes pending on a pooled connection for the next caller.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

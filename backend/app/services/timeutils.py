from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.core.config import settings


def now() -> datetime:
    """Canonical UTC clock — all deadline math uses this."""
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    """Wall-clock time in the user's configured zone, for time-of-day context only."""
    try:
        return datetime.now(ZoneInfo(settings.LOCAL_TZ))
    except Exception:
        return now()


def hours_until(dt: datetime) -> float:
    if dt is None:
        return 1e9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now()).total_seconds() / 3600.0


def local_today():
    """Calendar date in the user's zone — the unit habits and day views work in."""
    return local_now().date()


def start_of_local_day(offset_days: int = 0) -> datetime:
    """UTC instant at which the local day (today + offset) begins."""
    from datetime import timedelta
    d = local_now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)
    return d.astimezone(timezone.utc)


def local_month_bounds():
    """(start, end) UTC instants bounding the current local calendar month."""
    from datetime import timedelta
    ln = local_now()
    start = ln.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start.astimezone(timezone.utc), nxt.astimezone(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Coerce a value read back from the database to an aware UTC datetime.

    Postgres returns timezone-aware values for `DateTime(timezone=True)`;
    SQLite (used by the tests) returns naive ones. Storage is always UTC, so a
    naive value is UTC that lost its label — comparing without this raises
    "can't compare offset-naive and offset-aware datetimes".
    """
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_local(dt: datetime | None) -> datetime | None:
    """Convert a stored UTC instant to the user's configured wall clock."""
    dt = as_utc(dt)
    if dt is None:
        return None
    try:
        return dt.astimezone(ZoneInfo(settings.LOCAL_TZ))
    except Exception:
        return dt


def local_hhmm(dt: datetime | None, fallback: str = "--:--") -> str:
    """Clock time as the user would read it.

    Storage is UTC and day windows are computed in the local zone, so formatting
    a stored instant directly renders the wrong hour for any non-UTC user — an
    item at 00:00 local would display as 18:30. Everything the API returns as a
    clock string goes through here.
    """
    local = to_local(dt)
    return local.strftime("%H:%M") if local else fallback

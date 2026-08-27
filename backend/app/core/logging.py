"""Structured JSON logging with a per-request correlation id.

Every log line carries `request_id`, so one user action can be traced across
the router, the service layer and a JOCasta tool execution. Development gets a
readable single-line format instead of JSON.

REDACTION: `scrub()` strips anything that looks like a credential before it can
reach a log line. Passwords, tokens, API keys and Authorization headers must
never be logged, so the redaction lives here rather than at each call site.
"""
import json
import logging
import sys
import uuid
from contextvars import ContextVar

from app.core.config import settings

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

SENSITIVE = ("password", "secret", "token", "api_key", "apikey", "authorization",
             "credential", "hashed_password", "client_secret", "access_token",
             "refresh_token", "encrypted_token")

REDACTED = "[redacted]"


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


def scrub(value, _depth: int = 0):
    """Recursively redact credential-shaped values. Depth-capped so a cyclic or
    very deep structure can't stall logging."""
    if _depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            k: (REDACTED if any(s in str(k).lower() for s in SENSITIVE) else scrub(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(v, _depth + 1) for v in value[:20]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(scrub(extra))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Readable local format — same fields, one line, no JSON noise."""
    def format(self, record: logging.LogRecord) -> str:
        extra = getattr(record, "extra_fields", None)
        tail = ""
        if extra:
            tail = "  " + " ".join(f"{k}={v}" for k, v in scrub(extra).items())
        base = f"{record.levelname:<7} [{get_request_id()}] {record.name}: {record.getMessage()}{tail}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ConsoleFormatter() if settings.is_development else JsonFormatter())
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())
    # uvicorn duplicates access lines through its own handlers; route them here
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")


def log(logger: logging.Logger, level: int, message: str, **fields):
    """Emit a structured line: log(lg, logging.INFO, "tool ran", tool="create_task")."""
    logger.log(level, message, extra={"extra_fields": fields})

"""The one place EXPRESS talks to a language model.

Provider: **Google Gemini**, Developer API, via Google's official `google-genai`
SDK. Both callers — `brain` (conversation) and `planner_llm` (tool selection) —
come through here, so the key, the model id, the timeout policy and the health
record exist once instead of twice.

The model is a *language* faculty and nothing more. It never receives a database
session, a user row, or an id it was not handed as text in this turn; it cannot
execute anything. `planner_llm` turns its function calls back into the same
intent dicts the rule planner emits, and those go through the existing
validation, ownership, safety and confirmation layers before any write happens.
Automatic function calling is switched off explicitly below so the SDK cannot
invoke anything on its own.

Every failure here is survivable: callers fall back to the deterministic rules.
"""
import logging
import threading

from app.core.config import settings
from app.core.logging import log

logger = logging.getLogger("express.jocasta.llm")

PROVIDER = "gemini"

#: Finish reasons that mean the model declined rather than answered. Treated as
#: "no reply" so the caller falls back, rather than surfacing an empty string.
REFUSAL_REASONS = {
    "SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION",
    "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION",
}

#: Provider health, as observed. Deliberately *not* a guess from the key's
#: presence: a key that is set but expired, revoked, rate-limited or out of
#: quota must show up as broken rather than as unexplained fallback replies.
#: This is what /ready reports, and it never costs an API call to read.
_last_error: str | None = None
_last_ok: bool = False


def configured() -> bool:
    """A key is present. Says nothing about whether it works — see status()."""
    return bool(settings.GEMINI_API_KEY)


def model() -> str:
    return settings.GEMINI_MODEL


#: One client, reused. Not just an optimisation: a client built inline and left
#: unreferenced is collected mid-request and closes its own connection pool, so
#: the call fails with "the client has been closed" rather than answering.
#: Holding it here removes that failure mode instead of relying on every caller
#: to keep a local reference. Keyed by the settings it was built from, so
#: changing the key or timeout rebuilds rather than silently using the old one.
_client = None
_client_key: tuple | None = None
_client_lock = threading.Lock()


def client():
    """The shared Gemini client. Raises if the SDK is missing or misconfigured."""
    global _client, _client_key
    from google import genai            # imported lazily so the dep is optional
    from google.genai import types

    fingerprint = (settings.GEMINI_API_KEY, settings.JOCASTA_TIMEOUT_SECONDS,
                   settings.JOCASTA_MAX_RETRIES)
    with _client_lock:
        if _client is None or _client_key != fingerprint:
            _client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    timeout=int(settings.JOCASTA_TIMEOUT_SECONDS * 1000),  # ms
                    # `attempts` counts the first try; the setting counts
                    # retries after it.
                    retry_options=types.HttpRetryOptions(
                        attempts=max(1, settings.JOCASTA_MAX_RETRIES + 1),
                        # The free tier returns 503 "high demand" and 429 often
                        # enough that failing the turn on the first one would
                        # make JOCasta look broken when it is merely busy.
                        http_status_codes=[429, 500, 502, 503, 504]),
                ),
            )
            _client_key = fingerprint
        return _client


def reset_client() -> None:
    """Drop the cached client. For tests, which swap the SDK under us."""
    global _client, _client_key
    with _client_lock:
        _client, _client_key = None, None


def note_ok() -> None:
    global _last_error, _last_ok
    _last_error, _last_ok = None, True


def note_failure(exc: Exception, where: str) -> None:
    """Record a provider failure for readiness, and log it.

    Logged rather than silent: without this, a shut-down model id, a revoked key
    or an exhausted quota looks exactly like normal operation while quietly
    degrading every reply. That is the failure mode this project has already
    been bitten by once.
    """
    global _last_error, _last_ok
    _last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
    _last_ok = False
    log(logger, logging.WARNING, "gemini call failed, falling back",
        where=where, error=type(exc).__name__, detail=str(exc)[:200],
        model=settings.GEMINI_MODEL)


def refusal_reason(resp) -> str | None:
    """The finish reason, if the model declined instead of answering."""
    for cand in (getattr(resp, "candidates", None) or []):
        reason = getattr(cand, "finish_reason", None)
        name = getattr(reason, "name", None) or (str(reason) if reason else "")
        if name.upper() in REFUSAL_REASONS:
            return name.upper()
    return None


def status() -> dict:
    """What is actually known about the conversational layer.

    `configured` and `working` are separate on purpose. A key being present is
    not evidence that a call will succeed, and reporting it as though it were is
    how a billing or quota problem gets mistaken for a wiring problem. Reading
    this makes no API call, so it is safe on a health check.
    """
    if not configured():
        return {"provider": PROVIDER, "configured": False, "working": False,
                "using": "rules", "model": None,
                "detail": "No GEMINI_API_KEY set — replies come from the "
                          "deterministic layer."}
    if _last_error:
        return {"provider": PROVIDER, "configured": True, "working": False,
                "using": "rules", "model": model(), "detail": _last_error}
    if _last_ok:
        return {"provider": PROVIDER, "configured": True, "working": True,
                "using": "llm", "model": model(), "detail": ""}
    return {"provider": PROVIDER, "configured": True, "working": None,
            "using": "unverified", "model": model(),
            "detail": "Key configured but no call has been made yet this run."}

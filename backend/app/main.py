import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core import errors
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure as configure_logging, log, new_request_id, set_request_id
from app.api.routes import (auth, tasks, assignments, misc, jocasta, college, planner,
                            learning, projects, career, personal, goals, memory,
                            progress, finance, integrations)

configure_logging()
logger = logging.getLogger("express.api")

app = FastAPI(
    title=settings.APP_NAME,
    # Interactive docs are a development convenience, not a production surface.
    docs_url="/docs" if settings.is_development else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

errors.install(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tag every request with an id, echo it back, and log how it went.

    The client may supply X-Request-ID to correlate across a whole user action;
    otherwise one is minted here.
    """
    rid = request.headers.get("X-Request-ID") or new_request_id()
    set_request_id(rid)
    started = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        # The exception handlers build the body; this only records timing.
        log(logger, logging.ERROR, "request failed",
            method=request.method, path=request.url.path,
            ms=round((time.perf_counter() - started) * 1000, 1))
        raise
    ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    # Health probes would otherwise dominate the log.
    if request.url.path not in ("/health", "/ready"):
        log(logger,
            logging.WARNING if response.status_code >= 500 else logging.INFO,
            "request",
            method=request.method, path=request.url.path,
            status=response.status_code, ms=ms)
    return response


for r in (auth, tasks, assignments, college, planner, learning, projects, career,
          personal, goals, memory, progress, finance, integrations, jocasta, misc):
    app.include_router(r.router)


@app.get("/health", tags=["ops"])
def health():
    """Liveness: the process is up. Deliberately does not touch the database, so
    a database outage doesn't cause the orchestrator to kill a healthy app."""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.get("/ready", tags=["ops"])
def ready(response: Response):
    """Readiness: the app can actually serve traffic. Reports each dependency
    rather than a bare boolean, so a failing probe says what is wrong."""
    checks: dict[str, dict] = {}

    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        log(logger, logging.ERROR, "readiness: database unreachable", error=type(exc).__name__)
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    # Not a failure either way: JOCasta falls back to the deterministic layer.
    # But "a key is set" is not the same as "the key works", and conflating them
    # turns a billing or credential problem into an apparent wiring problem.
    from app.jocasta import brain
    state = brain.status()
    checks["jocasta_llm"] = {
        "ok": True,                        # the app serves regardless
        "provider": state["provider"],
        "configured": state["configured"],
        "working": state["working"],       # True / False / None (not yet tried)
        "answering_with": state["using"],  # "llm" | "rules" | "unverified"
        "model": state["model"],
        "detail": state["detail"],
    }

    ready_now = all(c.get("ok") for c in checks.values())
    if not ready_now:
        response.status_code = 503
    return {"ready": ready_now, "env": settings.ENV, "checks": checks}

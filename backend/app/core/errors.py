"""Uniform error responses.

Every failure leaves the API in the same shape:

    {"detail": "...", "error": "not_found", "request_id": "a1b2c3d4e5f6"}

so the frontend can render one message and the user can quote one id. An
unhandled exception is logged with its traceback but never returns that
traceback to the client outside development — a stack trace can disclose file
paths, query fragments and configuration.
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.logging import get_request_id, log

logger = logging.getLogger("express.error")

STATUS_SLUG = {
    400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
    409: "conflict", 422: "validation_error", 429: "rate_limited", 500: "internal_error",
}


def _body(status: int, detail, error: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "detail": detail,
            "error": error or STATUS_SLUG.get(status, "error"),
            "request_id": get_request_id(),
        },
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            log(logger, logging.ERROR, "http error",
                status=exc.status_code, path=request.url.path, detail=str(exc.detail))
        return _body(exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Field-level detail is safe and genuinely useful to the client.
        fields = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"),
             "message": e.get("msg", "invalid")}
            for e in exc.errors()
        ]
        log(logger, logging.INFO, "validation rejected",
            path=request.url.path, fields=[f["field"] for f in fields])
        return _body(422, fields, "validation_error")

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        # A constraint violation is the caller's problem, not a server fault —
        # but the driver message can quote table and column names, so it is
        # logged rather than returned.
        log(logger, logging.WARNING, "integrity violation",
            path=request.url.path, orig=str(getattr(exc, "orig", exc))[:300])
        return _body(409, "That conflicts with data that already exists.", "conflict")

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        log(logger, logging.ERROR, "database error", path=request.url.path, exc_info=True)
        logger.exception("database error")
        return _body(503, "The database is unavailable. Please retry.", "database_unavailable")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled exception", extra={"extra_fields": {"path": request.url.path}})
        detail = (f"{type(exc).__name__}: {exc}" if settings.expose_error_detail
                  else "Something went wrong on our side.")
        return _body(500, detail, "internal_error")

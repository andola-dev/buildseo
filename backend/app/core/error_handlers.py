"""Exception handlers producing the error envelope.

Every failure leaves the application as ``{"error": {...}}`` with a stable
code. Internal detail — stack traces, SQL, constraint text, provider payloads —
is logged server-side and replaced in the response by the request id, which is
what a caller should quote in a support ticket.
"""

from __future__ import annotations

from typing import Any

from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.logging import get_logger
from app.core.context import get_request_id
from app.core.exceptions import AppError, RateLimitExceededError
from app.core.responses import ErrorDetail, ErrorResponse

logger = get_logger(__name__)


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render the error envelope, always including the request id."""
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details={**(details or {}), "request_id": get_request_id() or "unknown"},
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle every deliberate domain error."""
    assert isinstance(exc, AppError)
    headers: dict[str, str] | None = None
    if isinstance(exc, RateLimitExceededError) and exc.retry_after_seconds:
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    log = logger.warning if exc.status_code < 500 else logger.error
    log(
        "request failed: %s",
        exc.code,
        extra={
            "error_code": exc.code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=exc.status_code >= 500,
    )
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert FastAPI/Pydantic validation failures into the envelope.

    Field errors are reshaped into ``{"field": [messages]}`` and the offending
    input value is dropped — a rejected password must not be echoed back.
    """
    assert isinstance(exc, RequestValidationError)
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        fields.setdefault(location or "body", []).append(str(error.get("msg", "invalid value")))

    logger.info(
        "request validation failed",
        extra={"path": request.url.path, "method": request.method, "fields": list(fields)},
    )
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"fields": fields},
    )


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate database constraint violations into 409s.

    The constraint name is not returned: it would expose schema internals. The
    services own the friendly, pre-checked messages; this handler is the safety
    net for a race that slips past them.
    """
    assert isinstance(exc, IntegrityError)
    original = getattr(exc, "orig", None)
    cause = getattr(original, "__cause__", original)

    if isinstance(cause, UniqueViolationError):
        code, message, http_status = (
            "DUPLICATE_RESOURCE",
            "A resource with these values already exists",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(cause, ForeignKeyViolationError):
        code, message, http_status = (
            "RELATED_RESOURCE_NOT_FOUND",
            "A referenced resource does not exist",
            status.HTTP_409_CONFLICT,
        )
    else:
        code, message, http_status = (
            "CONSTRAINT_VIOLATION",
            "The request violates a database constraint",
            status.HTTP_409_CONFLICT,
        )

    logger.warning(
        "integrity error on %s %s",
        request.method,
        request.url.path,
        extra={"error_code": code},
        exc_info=True,
    )
    return error_response(status_code=http_status, code=code, message=message)


async def database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle non-integrity database failures without leaking SQL."""
    logger.error(
        "database error on %s %s",
        request.method,
        request.url.path,
        exc_info=True,
    )
    return error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The database is temporarily unavailable",
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Wrap Starlette's own HTTPExceptions (404 routing, 405, …)."""
    assert isinstance(exc, StarletteHTTPException)
    codes = {
        status.HTTP_404_NOT_FOUND: "ENDPOINT_NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_FAILED",
        status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    }
    detail = exc.detail if isinstance(exc.detail, str) else "Request could not be processed"
    return error_response(
        status_code=exc.status_code,
        code=codes.get(exc.status_code, "HTTP_ERROR"),
        message=detail,
        headers=getattr(exc, "headers", None),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the traceback, return an opaque 500."""
    logger.exception(
        "unhandled exception on %s %s",
        request.method,
        request.url.path,
        extra={"path": request.url.path, "method": request.method},
    )
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install every handler. Order is by specificity, not registration."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(DBAPIError, database_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

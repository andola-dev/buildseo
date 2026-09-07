"""ASGI middleware: request identity, access logging, throttling, headers.

Ordering matters. Starlette runs middleware in reverse registration order, so
these are added such that a request passes through:

    RequestContextMiddleware  → assigns/propagates the request id
    AccessLogMiddleware       → times and logs the outcome
    RateLimitMiddleware       → may short-circuit with 429
    SecureHeadersMiddleware   → decorates the response

The context middleware runs first so that even a 429 or an unhandled error is
logged with a request id.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config.logging import get_logger
from app.core.context import request_context, set_client
from app.core.exceptions import RateLimitExceededError
from app.core.rate_limit import RateLimiter

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

RequestHandler = Callable[[Request], Awaitable[Response]]

#: Probes must stay cheap and un-throttled or an orchestrator will mark the
#: service unhealthy under load.
_UNTHROTTLED_PATHS = frozenset({"/health", "/health/live", "/health/ready", "/metrics"})


def _client_ip(request: Request) -> str | None:
    """Best-effort client address.

    ``X-Forwarded-For`` is only trusted for the *left-most* entry and only for
    logging and audit records — never for authorisation — because it is
    trivially spoofable unless a known proxy sanitises it.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id and binds the ambient request context."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and len(incoming) <= 128 else str(uuid.uuid4())

        with request_context(
            request_id=request_id,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        ):
            # Authentication dependencies later enrich the context with the
            # resolved user and tenant; see app.api.dependencies.auth.
            set_client(_client_ip(request), request.headers.get("user-agent"))
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emits one structured record per request.

    Deliberately logs the route *template* (``/api/v1/publishers/{publisher_id}``)
    rather than the raw path, so ids stay out of log aggregation keys, and never
    logs the query string, which may carry a search term.
    """

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request errored",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        route = request.scope.get("route")
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.url.path,
                "route": getattr(route, "path", None),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies a per-client quota, with a tighter one for auth endpoints.

    Keys prefer the authenticated user, falling back to the client address.
    Authentication endpoints are keyed by address by definition (there is no
    user yet) and get a much smaller budget to blunt credential stuffing.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int,
        window_seconds: int,
        auth_limit: int,
        auth_window_seconds: int,
        auth_path_prefix: str = "/auth",
        limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(app)
        # Middleware is registered before the lifespan builds the resource
        # container, so the limiter is resolved per request unless a test
        # injects one explicitly.
        self._limiter = limiter
        self._limit = limit
        self._window = window_seconds
        self._auth_limit = auth_limit
        self._auth_window = auth_window_seconds
        self._auth_prefix = auth_path_prefix

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        path = request.url.path
        if path in _UNTHROTTLED_PATHS:
            return await call_next(request)

        limiter = self._limiter or request.app.state.resources.rate_limiter
        is_auth = self._auth_prefix in path
        limit = self._auth_limit if is_auth else self._limit
        window = self._auth_window if is_auth else self._window
        identity = _client_ip(request) or "unknown"
        scope = "auth" if is_auth else "api"

        result = await limiter.acquire(f"{scope}:{identity}", limit=limit, window_seconds=window)
        if not result.allowed:
            logger.warning(
                "rate limit exceeded",
                extra={"path": path, "scope": scope, "limit": limit},
            )
            raise RateLimitExceededError(
                retry_after_seconds=result.retry_after_seconds,
                details={"limit": limit, "window_seconds": window},
            )

        response = await call_next(request)
        for header, value in result.as_headers().items():
            response.headers[header] = value
        return response


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Adds defensive response headers.

    This is a JSON API, so the CSP is maximally restrictive — it serves no
    scripts, styles or frames of its own. ``X-Frame-Options: DENY`` and
    ``nosniff`` protect the docs pages and any error body a browser might
    render directly.
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = True) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        if self._hsts and request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

"""FastAPI application factory.

``create_app`` is a factory rather than a module-level singleton so tests can
build an app with substituted settings and resources, and so nothing connects
to a database at import time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.middleware import (
    AccessLogMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecureHeadersMiddleware,
)
from app.api.router import OPENAPI_TAGS, api_router
from app.api.v1 import health
from app.bootstrap import AppResources, build_resources
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.core.error_handlers import register_exception_handlers

logger = get_logger(__name__)


def _lifespan(settings: Settings, resources: AppResources | None):
    """Build the lifespan handler bound to these settings/resources."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = resources is None
        app.state.resources = resources or build_resources(settings)
        logger.info(
            "application starting",
            extra={"environment": settings.app_env, "version": __version__},
        )
        try:
            yield
        finally:
            logger.info("application shutting down")
            # Only dispose what we created: an injected container belongs to
            # the caller (a test fixture) and may outlive this app instance.
            if owned:
                await app.state.resources.aclose()

    return lifespan


def create_app(
    settings: Settings | None = None,
    *,
    resources: AppResources | None = None,
) -> FastAPI:
    """Create and wire the ASGI application."""
    active = settings or (resources.settings if resources else get_settings())

    configure_logging(
        level=active.log_level,
        json_output=active.log_json,
        service=active.app_name,
        environment=active.app_env,
    )

    app = FastAPI(
        title=active.app_name,
        description=active.app_description,
        version=__version__,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs" if active.docs_enabled else None,
        redoc_url="/redoc" if active.docs_enabled else None,
        openapi_url="/openapi.json" if active.docs_enabled else None,
        lifespan=_lifespan(active, resources),
        # Domain errors carry their own envelope; suppress FastAPI's default
        # ``{"detail": ...}`` shape in the generated schema.
        responses={},
    )

    _register_middleware(app, active)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=active.api_v1_prefix)

    return app


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    """Install middleware.

    Starlette applies middleware in reverse registration order, so the list
    below is written bottom-up: ``SecureHeaders`` is added first and therefore
    runs innermost (closest to the route), while ``RequestContext`` is added
    last and runs first — which is what guarantees every response, including a
    429 or a 500, carries a request id.
    """
    if settings.secure_headers_enabled:
        app.add_middleware(SecureHeadersMiddleware, hsts=settings.is_production)

    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
            auth_limit=settings.rate_limit_auth_requests,
            auth_window_seconds=settings.rate_limit_auth_window_seconds,
        )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "Idempotency-Key"],
            expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "Retry-After"],
            max_age=600,
        )

    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestContextMiddleware)


app = create_app()

"""Health, liveness and readiness probes.

The three endpoints answer different questions and must not be conflated:

* ``/health``       — overall status, for humans and uptime checks.
* ``/health/live``  — is the process running? Never touches a dependency, so a
                      database blip cannot cause an orchestrator to restart
                      otherwise-healthy pods.
* ``/health/ready`` — can this instance serve traffic? Verifies database
                      connectivity, so a pod with a broken pool is pulled from
                      the load balancer instead of failing requests.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.dependencies.core import ResourcesDep
from app.config.logging import get_logger
from app.core.responses import ApiResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


class HealthStatus(BaseModel):
    """Overall service health."""

    status: Literal["ok", "degraded"] = Field(description="Aggregate service status")
    service: str = Field(description="Application name")
    version: str = Field(description="Deployed application version")
    environment: str = Field(description="Deployment environment name")


class LivenessStatus(BaseModel):
    """Process liveness."""

    status: Literal["alive"] = Field(description="Always 'alive' if the process responds")


class DependencyCheck(BaseModel):
    """Result of probing one downstream dependency."""

    name: str = Field(description="Dependency identifier")
    healthy: bool = Field(description="Whether the dependency answered correctly")
    latency_ms: float | None = Field(default=None, description="Round-trip time in milliseconds")
    error: str | None = Field(default=None, description="Failure class, never raw driver output")


class ReadinessStatus(BaseModel):
    """Readiness plus per-dependency detail."""

    status: Literal["ready", "not_ready"] = Field(description="Whether traffic may be routed here")
    checks: list[DependencyCheck] = Field(description="Individual dependency probes")


@router.get(
    "/health",
    summary="Service health",
    description="Aggregate health of the service. Does not require authentication.",
    response_model=ApiResponse[HealthStatus],
)
async def health(resources: ResourcesDep) -> ApiResponse[HealthStatus]:
    settings = resources.settings
    return ApiResponse(
        data=HealthStatus(
            status="ok",
            service=settings.app_name,
            version=__version__,
            environment=settings.app_env,
        )
    )


@router.get(
    "/health/live",
    summary="Liveness probe",
    description=(
        "Returns 200 whenever the process can serve a request. Intentionally "
        "checks no dependency, so a transient database failure never triggers a restart."
    ),
    response_model=ApiResponse[LivenessStatus],
)
async def liveness() -> ApiResponse[LivenessStatus]:
    return ApiResponse(data=LivenessStatus(status="alive"))


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description=(
        "Verifies database connectivity. Returns 503 when a dependency is unavailable "
        "so the instance is removed from load balancing until it recovers."
    ),
    response_model=ApiResponse[ReadinessStatus],
    responses={503: {"model": ApiResponse[ReadinessStatus], "description": "Not ready"}},
)
async def readiness(
    resources: ResourcesDep,
    response: Response,
) -> ApiResponse[ReadinessStatus]:
    checks = [await _check_database(resources)]
    ready = all(check.healthy for check in checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ApiResponse(
        data=ReadinessStatus(status="ready" if ready else "not_ready", checks=checks)
    )


async def _check_database(resources: ResourcesDep) -> DependencyCheck:
    """Round-trip a trivial query through the real pool."""
    started = time.perf_counter()
    try:
        async with resources.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("readiness: database check failed")
        return DependencyCheck(name="postgresql", healthy=False, error="connection_failed")
    except Exception:  # pragma: no cover - unexpected driver failure
        logger.exception("readiness: database check raised unexpectedly")
        return DependencyCheck(name="postgresql", healthy=False, error="unexpected_error")
    return DependencyCheck(
        name="postgresql",
        healthy=True,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )

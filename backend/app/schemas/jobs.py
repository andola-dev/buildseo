"""Background job schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import ReadSchemaBase


class JobRead(ReadSchemaBase):
    """A queued or completed unit of background work."""

    id: UUID
    task_name: str
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Handler arguments. Never contains a secret."
    )
    status: str
    attempts: int
    max_attempts: int
    run_at: datetime = Field(description="Earliest execution time; also the retry backoff")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobAccepted(ReadSchemaBase):
    """Returned by endpoints that enqueue work instead of doing it inline."""

    job_id: UUID
    task_name: str
    status: str
    poll_url: str = Field(description="Where to check progress")

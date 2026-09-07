"""Task queue abstraction.

PostgreSQL is the queue for the MVP. That is a deliberate choice rather than a
shortcut:

* ``SELECT … FOR UPDATE SKIP LOCKED`` gives safe multi-worker claiming with no
  extra infrastructure to run, secure and back up;
* enqueueing is **transactional with the domain change that caused it**, so a
  request that rolls back cannot leave an orphaned job, and a job cannot
  reference a row that was never committed — a guarantee an external broker
  cannot give without an outbox;
* the queue is tenant-scoped like everything else, so a job carries the tenant
  context its handler needs.

``TaskQueue`` is a Protocol so Celery, Dramatiq, ARQ or Temporal can replace
the implementation when the volume justifies the operational cost. No business
code imports this module's concrete classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.enums import JobStatus
from app.core.ids import uuid7
from app.db.session import TenantAwareSession
from app.models.jobs import Job
from app.repositories.jobs import JobRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EnqueuedTask:
    """Handle returned by an enqueue call."""

    job_id: UUID
    task_name: str
    status: str

    @property
    def poll_url(self) -> str:
        return f"/api/v1/jobs/{self.job_id}"


@dataclass(slots=True)
class TaskEnvelope:
    """A claimed unit of work, as a handler receives it."""

    job_id: UUID
    tenant_id: UUID
    task_name: str
    payload: dict[str, Any]
    attempts: int
    enqueued_by_user_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TaskQueue(Protocol):
    """Schedules deferred work."""

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
        max_attempts: int | None = None,
        idempotency_key: str | None = None,
        enqueued_by_user_id: UUID | None = None,
    ) -> EnqueuedTask:
        """Schedule ``task_name``.

        Payloads must be JSON-serialisable and must never contain a secret:
        handlers resolve credentials themselves through the credential service.
        """
        ...


class PostgresTaskQueue:
    """Enqueues jobs into the ``jobs`` table for the active tenant."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        jobs: JobRepository,
        audit: AuditService,
        default_max_attempts: int = 3,
    ) -> None:
        self._session = session
        self._jobs = jobs
        self._audit = audit
        self._default_max_attempts = default_max_attempts

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
        max_attempts: int | None = None,
        idempotency_key: str | None = None,
        enqueued_by_user_id: UUID | None = None,
    ) -> EnqueuedTask:
        if idempotency_key:
            existing = await self._jobs.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                # A retried request must not schedule the same work twice.
                return EnqueuedTask(
                    job_id=existing.id,
                    task_name=existing.task_name,
                    status=existing.status,
                )

        job = self._jobs.new(
            id=uuid7(),
            task_name=task_name,
            payload=payload,
            status=JobStatus.PENDING.value,
            max_attempts=max_attempts or self._default_max_attempts,
            run_at=datetime.now(UTC) + timedelta(seconds=max(0, delay_seconds)),
            enqueued_by_user_id=enqueued_by_user_id,
            idempotency_key=idempotency_key,
        )
        await self._jobs.flush()

        await self._audit.record(
            AuditAction.JOB_ENQUEUED,
            resource_type="job",
            resource_id=job.id,
            metadata={"task_name": task_name, "job_id": str(job.id)},
        )
        logger.info("job enqueued", extra={"task_name": task_name, "job_id": str(job.id)})
        return EnqueuedTask(job_id=job.id, task_name=task_name, status=job.status)

    async def get(self, job_id: UUID) -> Job:
        return await self._jobs.get_or_raise(job_id, resource="job")


class InMemoryTaskQueue:
    """Records enqueues without a database. Used by tests.

    Lets a test assert that an endpoint scheduled the right work without
    running a worker or touching the ``jobs`` table.
    """

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
        max_attempts: int | None = None,
        idempotency_key: str | None = None,
        enqueued_by_user_id: UUID | None = None,
    ) -> EnqueuedTask:
        self.enqueued.append((task_name, payload))
        return EnqueuedTask(job_id=uuid7(), task_name=task_name, status=JobStatus.PENDING.value)

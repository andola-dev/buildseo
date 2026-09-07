"""Background job data access (the queue's storage layer)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import JobStatus
from app.models.jobs import Job
from app.repositories.base import BaseRepository, TenantRepository


class JobRepository(TenantRepository[Job]):
    """Tenant-scoped job inspection and enqueueing."""

    model = Job
    sortable_fields = frozenset({"created_at", "updated_at", "status", "task_name", "run_at"})
    default_sort = "created_at"

    async def get_by_idempotency_key(self, key: str) -> Job | None:
        result = await self.session.execute(self._select().where(Job.idempotency_key == key))
        return result.scalar_one_or_none()

    def build_filters(
        self, *, status: str | None = None, task_name: str | None = None
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Job.status == status)
        if task_name:
            filters.append(Job.task_name == task_name)
        return filters


class JobClaimRepository(BaseRepository[Job]):
    """Cross-tenant job claiming, used only by the worker.

    Deliberately *not* a ``TenantRepository``: a worker serves every tenant, so
    it must be able to see the whole queue in order to pick the next job. It
    then re-establishes that job's tenant context before running the handler,
    so the handler itself is as confined as an HTTP request would be.

    This is the one place in the application that reads across tenants, which
    is why it lives in its own class with this docstring attached, rather than
    being an option on the tenant-scoped repository.
    """

    model = Job

    async def claim(self, *, batch_size: int, worker_id: str) -> list[Job]:
        """Atomically claim up to ``batch_size`` due jobs.

        ``FOR UPDATE SKIP LOCKED`` is what makes several workers safe against
        each other without a broker: each transaction locks the rows it takes
        and other workers step over them instead of blocking or double-running.
        """
        candidate_ids = (
            select(Job.id)
            .where(Job.status == JobStatus.PENDING.value, Job.run_at <= datetime.now(UTC))
            .order_by(Job.run_at.asc(), Job.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        ids = list((await self.session.execute(candidate_ids)).scalars().all())
        if not ids:
            return []

        claimed = (
            update(Job)
            .where(Job.id.in_(ids))
            .values(
                status=JobStatus.RUNNING.value,
                attempts=Job.attempts + 1,
                started_at=datetime.now(UTC),
                last_error=None,
            )
            .returning(Job)
        )
        result = await self.session.execute(claimed)
        rows = list(result.scalars().all())
        # Recorded on the row so a stuck job can be traced to a worker.
        for row in rows:
            row.payload = {**row.payload, "_worker_id": worker_id}
        return rows

    async def mark_succeeded(self, job: Job) -> None:
        job.status = JobStatus.SUCCEEDED.value
        job.finished_at = datetime.now(UTC)
        job.last_error = None
        await self.session.flush()

    async def mark_failed(self, job: Job, *, error: str, retry_backoff_seconds: int) -> None:
        """Fail a job, scheduling a retry while attempts remain.

        The error text is truncated because a provider or driver message can be
        arbitrarily long, and the whole row is read back by ``GET /jobs``.
        """
        job.last_error = error[:2000]
        if job.attempts < job.max_attempts:
            job.status = JobStatus.PENDING.value
            # Exponential backoff, so a persistently failing job does not spin.
            delay = retry_backoff_seconds * (2 ** (job.attempts - 1))
            job.run_at = datetime.now(UTC) + timedelta(seconds=delay)
            job.started_at = None
        else:
            job.status = JobStatus.FAILED.value
            job.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def requeue_stale(self, *, timeout_seconds: int) -> int:
        """Return jobs abandoned by a crashed worker to the queue.

        A worker that dies mid-job leaves the row RUNNING forever; without this
        sweep that work would be lost silently.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        statement = (
            update(Job)
            .where(
                Job.status == JobStatus.RUNNING.value,
                Job.started_at.is_not(None),
                Job.started_at < cutoff,
            )
            .values(
                status=JobStatus.PENDING.value,
                started_at=None,
                last_error=text("'worker timed out; requeued'"),
            )
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)

    async def get(self, job_id: UUID) -> Job | None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

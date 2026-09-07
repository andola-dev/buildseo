"""Worker entrypoint.

Claims jobs, re-establishes each job's tenant context, and runs its handler.

The tenant handshake is the important part: a worker serves every tenant, so
it must read the queue across tenants (``JobClaimRepository`` is the one
component allowed to) but then runs each handler inside a *separate*
tenant-scoped session. A handler is therefore as confined by RLS as an HTTP
request, and a bug in one handler cannot reach another tenant's rows.

Run with ``python -m app.workers.runner``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import sys
from datetime import UTC, datetime

from app.bootstrap import AppResources, build_resources
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.core.context import request_context
from app.db.session import session_scope
from app.repositories.jobs import JobClaimRepository
from app.repositories.tenants import TenantRepositoryGlobal
from app.services.factory import ServiceFactory
from app.workers import tasks as _tasks  # noqa: F401 - registers every handler
from app.workers.queue import TaskEnvelope
from app.workers.registry import registered_tasks, resolve

logger = get_logger(__name__)


class Worker:
    """Polls the queue and executes handlers."""

    def __init__(self, resources: AppResources, *, worker_id: str | None = None) -> None:
        self._resources = resources
        self._settings = resources.settings
        self._worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._stopping = asyncio.Event()

    def request_stop(self) -> None:
        """Finish the current batch, then exit. Wired to SIGTERM/SIGINT."""
        logger.info("worker stop requested", extra={"worker_id": self._worker_id})
        self._stopping.set()

    async def run(self) -> None:
        logger.info(
            "worker started",
            extra={"worker_id": self._worker_id, "tasks": list(registered_tasks())},
        )
        while not self._stopping.is_set():
            try:
                processed = await self._tick()
            except Exception:  # pragma: no cover - the loop must not die
                logger.exception("worker tick failed")
                processed = 0

            if processed == 0:
                # Idle: wait, but wake immediately on shutdown.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self._settings.worker_poll_interval_seconds
                    )
        logger.info("worker stopped", extra={"worker_id": self._worker_id})

    async def _tick(self) -> int:
        """Claim a batch and run each job. Returns how many ran."""
        # Requeue anything a crashed worker abandoned, or that work is lost.
        async with session_scope(self._resources.session_factory) as session:
            requeued = await JobClaimRepository(session).requeue_stale(
                timeout_seconds=self._settings.worker_job_timeout_seconds
            )
        if requeued:
            logger.warning("requeued stale jobs", extra={"requeued_count": requeued})

        # Claiming commits in its own transaction so the rows are marked
        # RUNNING even if a handler later crashes the process.
        async with session_scope(self._resources.session_factory) as session:
            claimed = await JobClaimRepository(session).claim(
                batch_size=self._settings.worker_batch_size, worker_id=self._worker_id
            )
            envelopes = [
                TaskEnvelope(
                    job_id=job.id,
                    tenant_id=job.tenant_id,
                    task_name=job.task_name,
                    payload={
                        key: value
                        for key, value in (job.payload or {}).items()
                        if key != "_worker_id"
                    },
                    attempts=job.attempts,
                    enqueued_by_user_id=job.enqueued_by_user_id,
                )
                for job in claimed
            ]

        for envelope in envelopes:
            await self._run_job(envelope)
        return len(envelopes)

    async def _run_job(self, envelope: TaskEnvelope) -> None:
        """Execute one job inside its own tenant-scoped transaction."""
        started = datetime.now(UTC)
        # Binds request_id/user/tenant so a job's logs and audit rows have the
        # same shape as a request's.
        with request_context(
            request_id=f"job:{envelope.job_id}",
            user_id=envelope.enqueued_by_user_id,
            tenant_id=envelope.tenant_id,
        ):
            handler = resolve(envelope.task_name)
            if handler is None:
                # An unknown name is a permanent failure: retrying cannot help.
                logger.error(
                    "no handler registered for task",
                    extra={"task_name": envelope.task_name, "job_id": str(envelope.job_id)},
                )
                await self._finish(envelope, error="unknown_task", permanent=True)
                return

            try:
                async with session_scope(
                    self._resources.session_factory,
                    tenant_id=envelope.tenant_id,
                    user_id=envelope.enqueued_by_user_id,
                ) as session:
                    tenant = await TenantRepositoryGlobal(session).get_by_id(envelope.tenant_id)
                    services = ServiceFactory(
                        session=session,
                        resources=self._resources,
                        tenant_settings=dict(tenant.settings) if tenant else {},
                    )
                    await asyncio.wait_for(
                        handler(envelope, services),
                        timeout=self._settings.worker_job_timeout_seconds,
                    )
            except TimeoutError:
                await self._finish(envelope, error="job_timeout")
                return
            except Exception as exc:
                logger.exception(
                    "job failed",
                    extra={"task_name": envelope.task_name, "job_id": str(envelope.job_id)},
                )
                await self._finish(envelope, error=f"{type(exc).__name__}: {exc}")
                return

            duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            await self._finish(envelope, error=None)
            logger.info(
                "job succeeded",
                extra={
                    "task_name": envelope.task_name,
                    "job_id": str(envelope.job_id),
                    "duration_ms": duration_ms,
                },
            )

    async def _finish(
        self, envelope: TaskEnvelope, *, error: str | None, permanent: bool = False
    ) -> None:
        """Record the outcome in a fresh transaction.

        Separate from the handler's transaction on purpose: a handler that
        failed has had its work rolled back, and the failure must still be
        recorded.
        """
        async with session_scope(self._resources.session_factory) as session:
            repository = JobClaimRepository(session)
            job = await repository.get(envelope.job_id)
            if job is None:  # pragma: no cover - deleted mid-flight
                return
            if error is None:
                await repository.mark_succeeded(job)
                return
            if permanent:
                # Skip the remaining attempts for an error retrying cannot fix.
                job.attempts = job.max_attempts
            await repository.mark_failed(
                job,
                error=error,
                retry_backoff_seconds=self._settings.worker_retry_backoff_seconds,
            )


async def _amain(settings: Settings | None = None) -> int:
    active = settings or get_settings()
    configure_logging(
        level=active.log_level,
        json_output=active.log_json,
        service=f"{active.app_name} worker",
        environment=active.app_env,
    )
    resources = build_resources(active)
    worker = Worker(resources)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.request_stop)

    try:
        await worker.run()
    finally:
        await resources.aclose()
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(main())

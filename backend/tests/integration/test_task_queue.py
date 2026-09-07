"""The PostgreSQL-backed queue.

Two properties matter and neither can be checked without a real database:

* ``FOR UPDATE SKIP LOCKED`` must let several workers claim from one queue
  without ever handing the same job to two of them, and without blocking;
* a job abandoned by a crashed worker must come back, because otherwise the
  work is lost silently.

The claim path is also the one place in the application that reads across
tenants, so the tests assert that a claimed job still carries the tenant its
handler will be confined to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bootstrap import AppResources
from app.core.enums import JobStatus
from app.db.session import TenantAwareSession
from app.models.jobs import Job
from app.repositories.jobs import JobClaimRepository, JobRepository
from app.services.factory import ServiceFactory
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _enqueue(
    session_factory: async_sessionmaker[TenantAwareSession],
    resources: AppResources,
    fixture: TenantFixture,
    *,
    task_name: str = "publisher.qualify",
    payload: dict[str, object] | None = None,
    idempotency_key: str | None = None,
    delay_seconds: int = 0,
) -> Job:
    """Enqueue through the real service graph, then return the row."""
    session = session_factory()
    await session.set_tenant_context(tenant_id=fixture.tenant_id, user_id=fixture.owner.id)
    try:
        services = ServiceFactory(session=session, resources=resources)
        handle = await services.task_queue.enqueue(
            task_name,
            payload or {"publisher_id": str(fixture.free_publisher.id)},
            idempotency_key=idempotency_key,
            enqueued_by_user_id=fixture.owner.id,
            delay_seconds=delay_seconds,
        )
        await session.commit()
        job = await JobRepository(session).get(handle.job_id)
        assert job is not None
        return job
    finally:
        await session.close()


async def _delete_job(
    session_factory: async_sessionmaker[TenantAwareSession], job_id: UUID
) -> None:
    async with session_factory() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
        if job is not None:
            await session.delete(job)
        await session.commit()


class TestEnqueue:
    async def test_enqueue_is_transactional_with_the_request(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        """A rolled-back request must not leave an orphaned job behind.

        This is the reason PostgreSQL is the queue rather than an external
        broker: no outbox pattern is needed to get this guarantee.
        """
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id)
        try:
            services = ServiceFactory(session=session, resources=resources)
            handle = await services.task_queue.enqueue("publisher.qualify", {"a": 1})
            await session.rollback()
        finally:
            await session.close()

        async with session_factory() as verifier:
            found = (
                await verifier.execute(select(Job).where(Job.id == handle.job_id))
            ).scalar_one_or_none()
            assert found is None

    async def test_enqueue_stamps_the_tenant_and_the_actor(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            assert job.tenant_id == tenant_a.tenant_id
            assert job.enqueued_by_user_id == tenant_a.owner.id
            assert job.status == JobStatus.PENDING.value
            assert job.attempts == 0
        finally:
            await _delete_job(session_factory, job.id)

    async def test_an_idempotency_key_makes_a_retry_a_no_op(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        first = await _enqueue(
            session_factory, resources, tenant_a, idempotency_key="qualify-publisher-1"
        )
        second = await _enqueue(
            session_factory, resources, tenant_a, idempotency_key="qualify-publisher-1"
        )
        try:
            assert first.id == second.id
            async with session_factory() as verifier:
                rows = (
                    (
                        await verifier.execute(
                            select(Job).where(Job.idempotency_key == "qualify-publisher-1")
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(list(rows)) == 1
        finally:
            await _delete_job(session_factory, first.id)

    async def test_the_same_key_in_another_tenant_is_a_separate_job(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """Keys are per workspace; one tenant cannot suppress another's work."""
        first = await _enqueue(session_factory, resources, tenant_a, idempotency_key="shared-key")
        second = await _enqueue(session_factory, resources, tenant_b, idempotency_key="shared-key")
        try:
            assert first.id != second.id
        finally:
            await _delete_job(session_factory, first.id)
            await _delete_job(session_factory, second.id)


class TestClaimSemantics:
    async def test_a_claim_marks_the_job_running_and_counts_the_attempt(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                claimed = await JobClaimRepository(session).claim(
                    batch_size=10, worker_id="worker-1"
                )
                await session.commit()

            ids = {row.id for row in claimed}
            assert job.id in ids
            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.status == JobStatus.RUNNING.value
                assert refreshed.attempts == 1
                assert refreshed.started_at is not None
                assert refreshed.payload["_worker_id"] == "worker-1"
        finally:
            await _delete_job(session_factory, job.id)

    async def test_two_workers_never_receive_the_same_job(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """``SKIP LOCKED`` in action: the second worker steps over locked rows.

        Both claims run inside open transactions, so the first worker's locks
        are still held when the second one looks.
        """
        jobs = [
            await _enqueue(session_factory, resources, tenant_a, payload={"n": 1}),
            await _enqueue(session_factory, resources, tenant_a, payload={"n": 2}),
            await _enqueue(session_factory, resources, tenant_b, payload={"n": 3}),
            await _enqueue(session_factory, resources, tenant_b, payload={"n": 4}),
        ]
        try:
            first_session = session_factory()
            second_session = session_factory()
            try:
                first = await JobClaimRepository(first_session).claim(
                    batch_size=2, worker_id="worker-1"
                )
                second = await JobClaimRepository(second_session).claim(
                    batch_size=2, worker_id="worker-2"
                )

                first_ids = {row.id for row in first}
                second_ids = {row.id for row in second}
                assert len(first_ids) == 2
                assert len(second_ids) == 2
                assert first_ids.isdisjoint(second_ids)

                await first_session.commit()
                await second_session.commit()
            finally:
                await first_session.close()
                await second_session.close()
        finally:
            for job in jobs:
                await _delete_job(session_factory, job.id)

    async def test_a_worker_sees_every_tenants_work(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """The one deliberate cross-tenant read, and it carries the tenant along.

        ``JobClaimRepository`` is not a ``TenantRepository``; the runner then
        re-establishes each job's ``tenant_id`` before invoking the handler.
        """
        first = await _enqueue(session_factory, resources, tenant_a)
        second = await _enqueue(session_factory, resources, tenant_b)
        try:
            async with session_factory() as session:
                claimed = await JobClaimRepository(session).claim(
                    batch_size=10, worker_id="worker-1"
                )
                await session.commit()

            by_id = {row.id: row for row in claimed}
            assert by_id[first.id].tenant_id == tenant_a.tenant_id
            assert by_id[second.id].tenant_id == tenant_b.tenant_id
        finally:
            await _delete_job(session_factory, first.id)
            await _delete_job(session_factory, second.id)

    async def test_a_delayed_job_is_not_claimed_early(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a, delay_seconds=3600)
        try:
            async with session_factory() as session:
                claimed = await JobClaimRepository(session).claim(
                    batch_size=10, worker_id="worker-1"
                )
                await session.commit()
            assert job.id not in {row.id for row in claimed}
        finally:
            await _delete_job(session_factory, job.id)

    async def test_an_empty_queue_claims_nothing(
        self, session_factory: async_sessionmaker[TenantAwareSession]
    ) -> None:
        async with session_factory() as session:
            assert await JobClaimRepository(session).claim(batch_size=5, worker_id="idle") == []


class TestFailureHandling:
    async def test_a_failure_with_attempts_left_is_retried_with_backoff(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                repository = JobClaimRepository(session)
                claimed = (await repository.claim(batch_size=1, worker_id="worker-1"))[0]
                await repository.mark_failed(
                    claimed, error="ProviderTimeout: upstream slow", retry_backoff_seconds=30
                )
                await session.commit()

            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.status == JobStatus.PENDING.value
                assert refreshed.started_at is None
                assert refreshed.last_error == "ProviderTimeout: upstream slow"
                # First retry: 30 * 2**0 seconds into the future.
                assert refreshed.run_at > datetime.now(UTC) + timedelta(seconds=20)
        finally:
            await _delete_job(session_factory, job.id)

    async def test_the_error_text_is_truncated(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        """A driver or provider message can be arbitrarily long; the row is read back."""
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                repository = JobClaimRepository(session)
                claimed = (await repository.claim(batch_size=1, worker_id="worker-1"))[0]
                await repository.mark_failed(claimed, error="x" * 5000, retry_backoff_seconds=30)
                await session.commit()

            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.last_error is not None
                assert len(refreshed.last_error) == 2000
        finally:
            await _delete_job(session_factory, job.id)

    async def test_the_last_attempt_fails_permanently(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                repository = JobClaimRepository(session)
                claimed = (await repository.claim(batch_size=1, worker_id="worker-1"))[0]
                # Simulate having exhausted the attempt budget.
                claimed.attempts = claimed.max_attempts
                await repository.mark_failed(claimed, error="boom", retry_backoff_seconds=30)
                await session.commit()

            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.status == JobStatus.FAILED.value
                assert refreshed.finished_at is not None
        finally:
            await _delete_job(session_factory, job.id)

    async def test_success_clears_the_error_and_stamps_the_finish(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                repository = JobClaimRepository(session)
                claimed = (await repository.claim(batch_size=1, worker_id="worker-1"))[0]
                await repository.mark_succeeded(claimed)
                await session.commit()

            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.status == JobStatus.SUCCEEDED.value
                assert refreshed.finished_at is not None
                assert refreshed.last_error is None
        finally:
            await _delete_job(session_factory, job.id)

    async def test_a_job_abandoned_by_a_crashed_worker_comes_back(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        """Without the sweep, a RUNNING row would sit there forever."""
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                repository = JobClaimRepository(session)
                await repository.claim(batch_size=1, worker_id="doomed-worker")
                await session.commit()

            # Backdate the claim to look like a worker that died an hour ago.
            async with session_factory() as session:
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(started_at=datetime.now(UTC) - timedelta(hours=1))
                )
                await session.commit()

            async with session_factory() as session:
                requeued = await JobClaimRepository(session).requeue_stale(timeout_seconds=300)
                await session.commit()
            assert requeued >= 1

            async with session_factory() as verifier:
                refreshed = (
                    await verifier.execute(select(Job).where(Job.id == job.id))
                ).scalar_one()
                assert refreshed.status == JobStatus.PENDING.value
                assert refreshed.started_at is None
                assert refreshed.last_error == "worker timed out; requeued"
        finally:
            await _delete_job(session_factory, job.id)

    async def test_a_freshly_claimed_job_is_not_requeued(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        job = await _enqueue(session_factory, resources, tenant_a)
        try:
            async with session_factory() as session:
                await JobClaimRepository(session).claim(batch_size=1, worker_id="worker-1")
                await session.commit()

            async with session_factory() as session:
                assert await JobClaimRepository(session).requeue_stale(timeout_seconds=300) == 0
                await session.commit()
        finally:
            await _delete_job(session_factory, job.id)


class TestTenantScopedJobViews:
    async def test_a_tenant_cannot_see_another_tenants_jobs(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """``GET /jobs`` is tenant-scoped even though the claim path is not."""
        mine = await _enqueue(session_factory, resources, tenant_a)
        theirs = await _enqueue(session_factory, resources, tenant_b)
        try:
            session = session_factory()
            await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
            try:
                repository = JobRepository(session)
                assert await repository.get(mine.id) is not None
                assert await repository.get(theirs.id) is None
            finally:
                await session.rollback()
                await session.close()
        finally:
            await _delete_job(session_factory, mine.id)
            await _delete_job(session_factory, theirs.id)

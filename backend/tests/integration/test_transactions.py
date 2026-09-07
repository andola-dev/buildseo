"""Transaction and tenant-context lifecycle.

``SET LOCAL`` is what keeps a pooled connection from carrying one tenant's
context into the next request. That property is worth asserting directly,
along with the two consequences it has for the application: a mid-request
commit must not silently drop the context, and a unit of work must roll back
in full when it fails.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.enums import PricingType, PublisherCategory, PublisherStatus, SubmissionMethod
from app.db.context import clear_tenant_context, read_tenant_context
from app.db.session import TenantAwareSession, session_scope
from app.models.publishers import Publisher
from app.repositories.publishers import PublisherRepository
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _publisher_values(slug: str) -> dict[str, object]:
    return {
        "domain": f"{slug}.test",
        "normalized_domain": f"{slug}.test",
        "website_url": f"https://{slug}.test",
        "name": slug,
        "category": PublisherCategory.BUSINESS_DIRECTORY.value,
        "submission_method": SubmissionMethod.MANUAL.value,
        "pricing_type": PricingType.FREE.value,
        "status": PublisherStatus.QUALIFIED.value,
    }


class TestTenantContextLifecycle:
    async def test_the_handshake_actually_reaches_postgresql(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Read the setting back from the server, not from our own bookkeeping."""
        async with session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            tenant_id, user_id = await read_tenant_context(session)
            assert tenant_id == tenant_a.tenant_id
            assert user_id == tenant_a.owner.id

    async def test_context_survives_a_mid_request_commit(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """``SET LOCAL`` dies with the transaction, so the session re-applies it.

        Without this, the statement after a mid-request commit would run with
        no tenant and — because RLS defaults to deny — silently see nothing.
        """
        async with session_factory() as session:
            await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
            await session.commit()

            tenant_id, _ = await read_tenant_context(session)
            assert tenant_id == tenant_a.tenant_id

            # And the repository still works, rather than returning empty.
            repository = PublisherRepository(session)
            assert await repository.count() == 2
            await session.rollback()

    async def test_context_survives_a_rollback(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        async with session_factory() as session:
            await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
            await session.rollback()
            tenant_id, _ = await read_tenant_context(session)
            assert tenant_id == tenant_a.tenant_id

    async def test_a_new_session_starts_with_no_context(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """The pool-hygiene property: no tenant leaks to the next borrower.

        The first session sets a tenant and returns its connection to the
        pool; the second may well be handed the same physical connection and
        must still see no context at all.
        """
        async with session_factory() as first:
            await first.set_tenant_context(tenant_id=tenant_a.tenant_id)
            assert (await read_tenant_context(first))[0] == tenant_a.tenant_id
            await first.rollback()

        async with session_factory() as second:
            assert await read_tenant_context(second) == (None, None)

    async def test_clearing_the_context_is_explicit_and_effective(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        async with session_factory() as session:
            await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
            await clear_tenant_context(session)
            assert await read_tenant_context(session) == (None, None)
            await session.rollback()

    async def test_context_does_not_leak_across_concurrent_sessions(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """Two open sessions hold two different tenants at the same time."""
        async with session_factory() as first, session_factory() as second:
            await first.set_tenant_context(tenant_id=tenant_a.tenant_id)
            await second.set_tenant_context(tenant_id=tenant_b.tenant_id)

            assert (await read_tenant_context(first))[0] == tenant_a.tenant_id
            assert (await read_tenant_context(second))[0] == tenant_b.tenant_id

            await first.rollback()
            await second.rollback()

    async def test_settings_are_transaction_local_on_the_server(
        self,
        engine: AsyncEngine,
        tenant_a: TenantFixture,
    ) -> None:
        """Asserted at the connection level, independent of our session class."""
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text("SELECT set_config('app.current_tenant_id', :value, true)"),
                    {"value": str(tenant_a.tenant_id)},
                )
                assert (await read_tenant_context(connection))[0] == tenant_a.tenant_id
            # The transaction has ended; PostgreSQL has discarded the setting.
            assert (await read_tenant_context(connection))[0] is None


class TestUnitOfWork:
    async def test_session_scope_commits_on_success(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        engine: AsyncEngine,
        tenant_a: TenantFixture,
    ) -> None:
        async with session_scope(session_factory, tenant_id=tenant_a.tenant_id) as session:
            PublisherRepository(session).new(**_publisher_values("committed-dir"))

        async with session_factory() as verifier:
            found = (
                await verifier.execute(
                    select(Publisher).where(Publisher.normalized_domain == "committed-dir.test")
                )
            ).scalar_one_or_none()
            assert found is not None
            await verifier.delete(found)
            await verifier.commit()

    async def test_session_scope_rolls_back_the_whole_unit_of_work(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """A failure anywhere leaves nothing behind — including the audit row.

        This is why the queue lives in PostgreSQL: an enqueue in a failed
        request disappears with the domain change that caused it.
        """

        class Boom(RuntimeError):
            pass

        with pytest.raises(Boom):
            async with session_scope(session_factory, tenant_id=tenant_a.tenant_id) as session:
                repository = PublisherRepository(session)
                repository.new(**_publisher_values("rolled-back-dir"))
                await repository.flush()
                raise Boom

        async with session_factory() as verifier:
            count = (
                (
                    await verifier.execute(
                        select(Publisher).where(
                            Publisher.normalized_domain == "rolled-back-dir.test"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(count) == []

    async def test_session_scope_applies_the_tenant_before_yielding(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """A worker's handler must be as confined as an HTTP request."""
        async with session_scope(
            session_factory, tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
        ) as session:
            assert session.tenant_id == tenant_a.tenant_id
            assert await read_tenant_context(session) == (
                tenant_a.tenant_id,
                tenant_a.owner.id,
            )

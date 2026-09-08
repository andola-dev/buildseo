"""The idempotency ledger.

A client that times out mid-POST cannot tell whether the write happened. The
ledger lets a replay return the original response instead of creating a second
publisher, opportunity or submission — while a key reused with a *different*
body is treated as the client bug it is.

Tested against the database because the guarantee is a stored record plus a
unique constraint, not a piece of in-process logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.dependencies.idempotency import IdempotencyGuard, request_fingerprint
from app.core.exceptions import IdempotencyConflictError
from app.db.session import TenantAwareSession
from app.models.idempotency import IdempotencyKey
from app.repositories.idempotency import IdempotencyKeyRepository
from tests.fixtures.tenants import TenantFixture

pytestmark = pytest.mark.integration

ENDPOINT = "POST /api/v1/opportunities"


@pytest_asyncio.fixture
async def session_a(
    session_factory: async_sessionmaker[TenantAwareSession], tenant_a: TenantFixture
) -> AsyncIterator[TenantAwareSession]:
    session = session_factory()
    await session.set_tenant_context(tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


class TestFingerprint:
    def test_key_order_does_not_change_the_fingerprint(self) -> None:
        """Otherwise a legitimate retry would look like a conflicting reuse."""
        assert request_fingerprint({"a": 1, "b": 2}) == request_fingerprint({"b": 2, "a": 1})

    def test_a_different_body_produces_a_different_fingerprint(self) -> None:
        assert request_fingerprint({"a": 1}) != request_fingerprint({"a": 2})

    def test_the_fingerprint_fits_the_column(self) -> None:
        """``request_hash`` is ``String(64)`` — a SHA-256 hex digest exactly."""
        assert len(request_fingerprint({"a": 1})) == 64


class TestGuard:
    async def test_a_first_request_has_no_prior_record(self, session_a: TenantAwareSession) -> None:
        guard = IdempotencyGuard(
            repository=IdempotencyKeyRepository(session_a), key="key-1", endpoint=ENDPOINT
        )
        assert await guard.existing({"target_url": "https://tenant-a-client.test/"}) is None

    async def test_a_replay_returns_the_stored_response(
        self, session_a: TenantAwareSession
    ) -> None:
        payload = {"target_url": "https://tenant-a-client.test/"}
        guard = IdempotencyGuard(
            repository=IdempotencyKeyRepository(session_a), key="key-2", endpoint=ENDPOINT
        )
        await guard.remember(
            payload, status_code=201, body={"id": "abc", "status": "DISCOVERED"}, resource_id="abc"
        )

        record = await guard.existing(payload)
        assert record is not None
        assert record.response_status == 201
        assert record.response_body == {"id": "abc", "status": "DISCOVERED"}
        assert record.resource_id == "abc"

    async def test_reusing_a_key_with_a_different_body_is_a_conflict(
        self, session_a: TenantAwareSession
    ) -> None:
        """409, rather than silently returning an unrelated earlier response."""
        guard = IdempotencyGuard(
            repository=IdempotencyKeyRepository(session_a), key="key-3", endpoint=ENDPOINT
        )
        await guard.remember(
            {"target_url": "https://tenant-a-client.test/a"},
            status_code=201,
            body={"id": "a"},
            resource_id="a",
        )

        with pytest.raises(IdempotencyConflictError) as raised:
            await guard.existing({"target_url": "https://tenant-a-client.test/b"})
        assert raised.value.status_code == 409
        assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"

    async def test_a_guard_with_no_key_stores_nothing(self, session_a: TenantAwareSession) -> None:
        """The header is optional; without it the endpoint behaves normally."""
        repository = IdempotencyKeyRepository(session_a)
        guard = IdempotencyGuard(repository=repository, key=None, endpoint=ENDPOINT)
        assert not guard.enabled
        await guard.remember({"a": 1}, status_code=201, body={"id": "x"}, resource_id="x")
        assert await repository.count() == 0

    async def test_the_same_key_on_another_endpoint_is_independent(
        self, session_a: TenantAwareSession
    ) -> None:
        repository = IdempotencyKeyRepository(session_a)
        payload = {"target_url": "https://tenant-a-client.test/"}
        await IdempotencyGuard(repository=repository, key="shared", endpoint=ENDPOINT).remember(
            payload, status_code=201, body={"id": "a"}, resource_id="a"
        )

        other = IdempotencyGuard(
            repository=repository, key="shared", endpoint="POST /api/v1/submissions"
        )
        assert await other.existing(payload) is None


class TestLedgerIsTenantScoped:
    async def test_one_tenants_key_is_invisible_to_another(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """Otherwise one workspace's retry could return another's response."""
        payload = {"target_url": "https://example.test/"}
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            await IdempotencyGuard(
                repository=IdempotencyKeyRepository(session), key="cross", endpoint=ENDPOINT
            ).remember(payload, status_code=201, body={"id": "a"}, resource_id="a")
            await session.commit()
        finally:
            await session.close()

        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_b.tenant_id)
        try:
            guard = IdempotencyGuard(
                repository=IdempotencyKeyRepository(session), key="cross", endpoint=ENDPOINT
            )
            # Not merely a different response — no record at all, so tenant B's
            # request proceeds normally.
            assert await guard.existing(payload) is None
        finally:
            await session.rollback()
            await session.close()


class TestRetention:
    async def test_the_sweep_only_removes_expired_keys(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """Keys are only useful for the length of a retry window."""
        repository = IdempotencyKeyRepository(session_a)
        stale = repository.new(key="stale", endpoint=ENDPOINT, request_hash="c" * 64)
        repository.new(key="fresh", endpoint=ENDPOINT, request_hash="d" * 64)
        await repository.flush()

        await session_a.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.id == stale.id)
            .values(created_at=datetime.now(UTC) - timedelta(days=30))
        )
        await session_a.flush()

        removed = await repository.purge_older_than(days=7)
        assert removed == 1
        assert await repository.get("stale", ENDPOINT) is None
        assert await repository.get("fresh", ENDPOINT) is not None

"""Idempotency key data access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.models.idempotency import IdempotencyKey
from app.repositories.base import TenantRepository


class IdempotencyKeyRepository(TenantRepository[IdempotencyKey]):
    model = IdempotencyKey
    sortable_fields = frozenset({"created_at"})
    default_sort = "created_at"

    async def get(self, key: str, endpoint: str) -> IdempotencyKey | None:  # type: ignore[override]
        result = await self.session.execute(
            self._select().where(IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint)
        )
        return result.scalar_one_or_none()

    async def purge_older_than(self, *, days: int) -> int:
        """Retention sweep. Keys are only useful for the length of a retry window."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.tenant_id == self.tenant_id,
                IdempotencyKey.created_at < cutoff,
            )
        )
        return int(result.rowcount or 0)

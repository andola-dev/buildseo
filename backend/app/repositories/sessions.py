"""Refresh session (token family) data access."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update

from app.models.sessions import RefreshSession
from app.repositories.base import BaseRepository


class RefreshSessionRepository(BaseRepository[RefreshSession]):
    """Server-side refresh tokens.

    Not tenant-scoped: refresh happens before a tenant is selected. Every
    lookup is by token *digest* or by user id, so there is no query that could
    return another user's sessions.
    """

    model = RefreshSession
    sortable_fields = frozenset({"created_at", "last_used_at", "expires_at"})
    default_sort = "created_at"

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        """Find a session by the digest of a presented token.

        Note the digest — never the token — is what touches the database, so a
        dump of this table cannot be replayed against the API.
        """
        result = await self.session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, session_id: UUID, user_id: UUID) -> RefreshSession | None:
        result = await self.session.execute(
            select(RefreshSession).where(
                RefreshSession.id == session_id, RefreshSession.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: UUID) -> list[RefreshSession]:
        result = await self.session.execute(
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked.is_(False),
                RefreshSession.expires_at > datetime.now(UTC),
            )
            .order_by(RefreshSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(self, session_row: RefreshSession, *, reason: str) -> None:
        session_row.revoked = True
        session_row.revoked_reason = reason
        session_row.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def revoke_family(self, family_id: UUID, *, reason: str) -> int:
        """Revoke every token in a family.

        The reuse-detection path: presenting an already-rotated token means the
        token leaked, so the entire lineage descended from that login is killed
        rather than just the replayed row.
        """
        statement = (
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked.is_(False))
            .values(revoked=True, revoked_reason=reason, revoked_at=datetime.now(UTC))
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: UUID, *, reason: str) -> int:
        """Used on password change and on explicit "sign out everywhere"."""
        statement = (
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked.is_(False))
            .values(revoked=True, revoked_reason=reason, revoked_at=datetime.now(UTC))
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)

    async def touch(self, session_row: RefreshSession) -> None:
        session_row.last_used_at = datetime.now(UTC)
        await self.session.flush()

    async def delete_expired(self, *, before: datetime | None = None) -> int:
        """Retention sweep for rows that can no longer authenticate anything."""
        cutoff = before or datetime.now(UTC)
        result = await self.session.execute(
            delete(RefreshSession).where(RefreshSession.expires_at < cutoff)
        )
        return int(result.rowcount or 0)

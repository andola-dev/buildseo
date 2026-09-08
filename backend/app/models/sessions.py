"""Server-side refresh sessions (token families).

Each login starts a *family*. Every rotation adds a row to the same family and
revokes its predecessor, which is what makes replay detectable: presenting an
already-revoked token means the token leaked, so the whole family is killed.

Only a SHA-256 digest of the token is stored — the raw refresh token exists
solely in the client's possession.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.users import User


class RefreshSession(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One refresh token in a family.

    Not tenant-owned: refresh happens before a tenant is selected, so this
    table carries no ``tenant_id`` and no RLS policy. ``active_tenant_id``
    merely remembers the last selected workspace so a refresh can restore it —
    it is re-validated against ``tenant_memberships`` like any other tenant
    claim and grants nothing on its own.
    """

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user_id_revoked", "user_id", "revoked"),
        Index("ix_refresh_sessions_family_id", "family_id"),
        Index(
            "ix_refresh_sessions_expires_at_live",
            "expires_at",
            postgresql_where=text("NOT revoked"),
        ),
        {"comment": "Refresh token families. Stores digests only, never tokens."},
    )

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: Groups every token descended from a single login.
    family_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Hex SHA-256 of the opaque token. Unique so a digest cannot be replayed
    #: across rows even in the event of a generation collision.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    active_tenant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: Why the row was revoked: ``rotated``, ``logout``, ``reuse_detected``,
    #: ``password_changed``, ``revoked_by_user``. Drives security auditing.
    revoked_reason: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise")

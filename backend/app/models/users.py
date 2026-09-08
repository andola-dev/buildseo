"""User identity.

``users`` is a *global* table: one human, one login, independent of how many
tenants they can reach. It therefore carries no ``tenant_id`` and is not behind
an RLS policy — it has to be reachable before a tenant is chosen, for login and
token refresh. Tenant-scoped visibility of users is provided by querying
through ``tenant_memberships`` (see ``UserRepository.list_for_tenant``), and
access is gated by membership validation in the dependency chain.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.sessions import RefreshSession
    from app.models.tenants import TenantMembership


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person who can authenticate."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_active", "is_active", postgresql_where=text("is_active")),
        {"comment": "Global user identities. Not tenant-owned; see module docstring."},
    )

    #: CITEXT gives case-insensitive uniqueness in the database itself, so
    #: "Ada@Example.com" cannot register alongside "ada@example.com".
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    #: Argon2id PHC string. Never serialised into any schema.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    #: Reserved for a future email-verification flow. No email is sent today.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: Platform staff flag. Grants nothing by itself — it never bypasses RLS or
    #: a permission check; it exists for future support tooling.
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ``lazy="raise"`` turns an accidental lazy load into an explicit error
    # instead of a MissingGreenlet deep inside serialisation; callers must ask
    # for what they need with selectinload/joinedload.
    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="user", lazy="raise", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user", lazy="raise", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str | None:
        parts = [part for part in (self.first_name, self.last_name) if part]
        return " ".join(parts) or None

    @property
    def identity_tokens(self) -> tuple[str, ...]:
        """Values a password must not contain (fed to the strength policy)."""
        return tuple(value for value in (self.email, self.first_name, self.last_name) if value)

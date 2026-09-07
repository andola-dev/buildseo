"""Tenants (customer workspaces) and their memberships."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MembershipStatus, TenantStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.rbac import MembershipRole
    from app.models.users import User


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A customer workspace. The root of every tenant-owned record.

    Like ``users`` this is a global table with no ``tenant_id`` of its own
    (its ``id`` *is* the tenant). It must be readable before a tenant is
    selected, so access is mediated by ``tenant_memberships`` rather than by an
    RLS policy.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(TenantStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'", name="slug_format"),
        {"comment": "Customer workspaces. Root of tenant ownership."},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Stable, URL-safe handle. Unique platform-wide.
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{TenantStatus.ACTIVE.value}'")
    )
    #: Non-sensitive workspace preferences (default country/language, scoring
    #: weight overrides). Never holds credentials.
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="tenant", lazy="raise", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE.value


class TenantMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Links a user to a tenant. The sole authority for tenant access.

    A user may hold memberships in many tenants with different roles in each,
    which is why the access token carries only a *currently selected* tenant
    and re-validates it here on every request.

    This table is tenant-owned and RLS-protected, with an extra permissive
    policy on ``user_id`` so a user can enumerate the tenants they may enter
    before any tenant context exists.
    """

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_id_user_id"),
        CheckConstraint(MembershipStatus.check_constraint("status"), name="status_valid"),
        Index("ix_tenant_memberships_user_id_status", "user_id", "status"),
        Index(
            "ix_tenant_memberships_tenant_id_owner",
            "tenant_id",
            postgresql_where=text("is_owner"),
        ),
        {"comment": "Tenant access grants. RLS: tenant match OR own user_id."},
    )

    # Declared explicitly rather than via TenantOwnedMixin so the composite
    # unique constraint above can reference it in a readable order.
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{MembershipStatus.ACTIVE.value}'")
    )
    #: Ownership marker used to protect ownership-level operations. Ownership is
    #: still expressed as permissions via the seeded Owner role; this flag
    #: guards transfer/deletion so the last owner cannot be removed.
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)

    tenant: Mapped[Tenant] = relationship(back_populates="memberships", lazy="raise")
    user: Mapped[User] = relationship(back_populates="memberships", lazy="raise")
    role_links: Mapped[list[MembershipRole]] = relationship(
        back_populates="membership", lazy="raise", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE.value

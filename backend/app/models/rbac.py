"""Roles, permissions and their links.

The shape is deliberately conventional:

    membership → membership_roles → roles → role_permissions → permissions

``permissions`` is a global, immutable catalog (no ``tenant_id``): a permission
code means the same thing everywhere, and letting tenants invent codes would
make authorisation unreviewable. ``roles`` *is* per tenant, so every workspace
gets its own editable copy of the five defaults and can add custom roles
without a schema change.

Effective permissions are the union across a member's roles, always loaded from
the database — never cached in a token.
"""

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
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.tenants import TenantMembership

if TYPE_CHECKING:  # pragma: no cover
    pass


class Permission(Base, UUIDPrimaryKeyMixin):
    """One granular capability, e.g. ``publisher.create``.

    Global and seeded; there is no API to create one. ``resource`` and
    ``action`` are stored split as well as joined so the UI can group a
    permission matrix without parsing strings.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),
        CheckConstraint("code = resource || '.' || action", name="code_matches_parts"),
        {"comment": "Global permission catalog. Seeded, not tenant-owned."},
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named bundle of permissions, scoped to one tenant."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_id_slug"),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9_]{1,62}[a-z0-9]$'", name="slug_format"),
        Index("ix_roles_tenant_id_is_system", "tenant_id", "is_system"),
        {"comment": "Per-tenant roles. System roles are seeded and protected."},
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: System roles are seeded per tenant. They may not be renamed or deleted,
    #: and their permission set may not be edited, so a tenant cannot lock
    #: itself out by stripping the Owner role.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    permission_links: Mapped[list[RolePermission]] = relationship(
        back_populates="role", lazy="raise", cascade="all, delete-orphan"
    )


class RolePermission(Base, UUIDPrimaryKeyMixin):
    """Grants one permission to one role.

    Carries ``tenant_id`` even though it is derivable from ``role_id``: the RLS
    policy needs a local discriminator column, and duplicating it avoids a join
    inside a policy predicate on every read.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        Index("ix_role_permissions_tenant_id_role_id", "tenant_id", "role_id"),
        {"comment": "Role-to-permission grants."},
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[Role] = relationship(back_populates="permission_links", lazy="raise")
    permission: Mapped[Permission] = relationship(lazy="raise")


class MembershipRole(Base, UUIDPrimaryKeyMixin):
    """Assigns a role to a membership. A member may hold several."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        UniqueConstraint("membership_id", "role_id", name="uq_membership_roles_membership_role"),
        Index("ix_membership_roles_tenant_id_membership_id", "tenant_id", "membership_id"),
        {"comment": "Role assignments per tenant membership."},
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant_memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    membership: Mapped[TenantMembership] = relationship(back_populates="role_links", lazy="raise")
    role: Mapped[Role] = relationship(lazy="raise")

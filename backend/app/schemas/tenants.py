"""Tenant and membership schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import EmailStr, Field, StringConstraints

from app.core.enums import MembershipStatus, TenantStatus
from app.schemas.common import ReadSchemaBase, RoleSlug, SchemaBase, Slug
from app.schemas.users import UserRead


class TenantCreate(SchemaBase):
    """Create a workspace. The caller becomes its owner."""

    name: Annotated[str, StringConstraints(min_length=2, max_length=200)]
    slug: Slug | None = Field(
        default=None, description="URL-safe handle; derived from the name when omitted"
    )


class TenantUpdate(SchemaBase):
    name: Annotated[str, StringConstraints(min_length=2, max_length=200)] | None = None
    status: TenantStatus | None = None
    settings: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Non-sensitive workspace preferences (default country/language, scoring "
            "weight overrides). Rejected if it contains secret-shaped keys."
        ),
    )


class TenantRead(ReadSchemaBase):
    id: UUID
    name: str
    slug: str
    status: str
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MembershipRead(ReadSchemaBase):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    status: str
    is_owner: bool
    roles: list[str] = Field(default_factory=list, description="Role slugs held")
    user: UserRead | None = Field(default=None, description="Member profile, when expanded")
    created_at: datetime
    updated_at: datetime


class MembershipCreate(SchemaBase):
    """Add an existing account to this workspace.

    Identifies the person by email because there is no email delivery in this
    phase: an operator adds an account that already exists rather than sending
    an invitation. ``user_id`` is accepted as an alternative when the caller
    already knows it.
    """

    email: EmailStr | None = None
    user_id: UUID | None = None
    role_slugs: list[RoleSlug] = Field(
        default_factory=lambda: ["viewer"],
        min_length=1,
        description="Roles to grant in this workspace",
    )
    status: MembershipStatus = Field(default=MembershipStatus.ACTIVE)


class MembershipUpdate(SchemaBase):
    status: MembershipStatus | None = None
    role_slugs: list[RoleSlug] | None = Field(
        default=None, min_length=1, description="Replaces the member's roles entirely"
    )
    is_owner: bool | None = Field(
        default=None,
        description="Grant or remove workspace ownership. The last active owner cannot be removed.",
    )

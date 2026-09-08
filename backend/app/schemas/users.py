"""User and profile schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, SecretStr

from app.schemas.common import ReadSchemaBase, SchemaBase


class UserRead(ReadSchemaBase):
    """A user as exposed by the API.

    Note what is absent: ``password_hash``. It is not omitted by configuration
    but simply not declared, so no future change to the model can leak it here.
    """

    id: UUID
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = Field(default=None, description="Convenience join of the name parts")
    is_active: bool
    is_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TenantMembershipSummary(ReadSchemaBase):
    """One workspace the caller belongs to, with their roles in it."""

    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    status: str = Field(description="Membership status; only ACTIVE grants access")
    is_owner: bool
    roles: list[str] = Field(default_factory=list, description="Role slugs held in this workspace")


class MeRead(ReadSchemaBase):
    """The authenticated user, their workspaces and their effective permissions."""

    user: UserRead
    active_tenant_id: UUID | None = Field(
        default=None, description="Workspace the current access token is scoped to"
    )
    tenants: list[TenantMembershipSummary] = Field(default_factory=list)
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Effective permission codes in the active workspace. Loaded per request, "
            "so a revoked role takes effect immediately rather than at token expiry."
        ),
    )


class UserUpdate(SchemaBase):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)


class PasswordChangeRequest(SchemaBase):
    """Change the caller's own password.

    Requires the current password even though the caller is authenticated: a
    stolen access token should not be enough to take over the account.
    """

    current_password: SecretStr
    new_password: SecretStr = Field(min_length=1, max_length=256)
    revoke_other_sessions: bool = Field(
        default=True,
        description=(
            "Sign out every other device. Defaults to true because a password "
            "change usually follows a suspected compromise."
        ),
    )

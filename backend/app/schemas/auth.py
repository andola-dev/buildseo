"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import EmailStr, Field, SecretStr, StringConstraints, field_validator

from app.core.security.password_policy import DEFAULT_POLICY
from app.schemas.common import ReadSchemaBase, SchemaBase, Slug

#: Passwords travel as ``SecretStr`` so an accidental ``repr`` of a request
#: model prints ``**********`` rather than the credential.
Password = Annotated[SecretStr, Field(min_length=1, max_length=256)]


class RegisterRequest(SchemaBase):
    """Create an account, optionally with a first workspace."""

    email: EmailStr = Field(description="Login address; must be unique platform-wide")
    password: Password = Field(description="Must satisfy the password policy")
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    tenant_name: Annotated[str, StringConstraints(min_length=2, max_length=200)] | None = Field(
        default=None,
        description=(
            "Name of a workspace to create and own. When omitted, the account is "
            "created without a workspace and must be added to one."
        ),
    )
    tenant_slug: Slug | None = Field(
        default=None, description="URL-safe workspace handle; derived from the name when omitted"
    )

    @field_validator("password")
    @classmethod
    def _check_strength(cls, value: SecretStr) -> SecretStr:
        """Fail fast on a weak password.

        Duplicated by ``PasswordHasher.validate_strength`` in the service layer
        (which also knows the user's name and email); this copy gives the
        caller a clean 422 with the full requirement list before any work.
        """
        problems = DEFAULT_POLICY.violations(value.get_secret_value())
        if problems:
            raise ValueError("password " + "; ".join(problems))
        return value


class LoginRequest(SchemaBase):
    email: EmailStr
    password: Password
    tenant_id: UUID | None = Field(
        default=None,
        description=(
            "Optionally select an active workspace during login. Membership is "
            "validated server-side; an unauthorised value is rejected."
        ),
    )


class RefreshRequest(SchemaBase):
    refresh_token: SecretStr = Field(description="The opaque refresh token previously issued")


class LogoutRequest(SchemaBase):
    refresh_token: SecretStr | None = Field(
        default=None, description="Revoke this specific session; omit to revoke the current one"
    )
    all_sessions: bool = Field(
        default=False, description="Revoke every session for the user (sign out everywhere)"
    )


class SelectTenantRequest(SchemaBase):
    tenant_id: UUID = Field(description="Workspace to make active for subsequent requests")


class TokenPair(ReadSchemaBase):
    """The credentials returned by login and refresh."""

    access_token: str = Field(description="Short-lived bearer token (JWT)")
    refresh_token: str = Field(description="Long-lived opaque token; store securely")
    token_type: str = Field(default="bearer", description="Always 'bearer'")
    expires_in: int = Field(description="Access token lifetime in seconds")
    expires_at: datetime = Field(description="Access token expiry (UTC)")
    active_tenant_id: UUID | None = Field(
        default=None, description="Workspace the access token is scoped to, if any"
    )


class AccessTokenResponse(ReadSchemaBase):
    """A new access token only — returned when switching workspace.

    The refresh token is deliberately not rotated here: switching workspace is
    not a re-authentication, and reissuing it on every switch would multiply
    the number of live tokens for no security gain.
    """

    access_token: str
    token_type: str = Field(default="bearer")
    expires_in: int
    expires_at: datetime
    active_tenant_id: UUID


class SessionRead(ReadSchemaBase):
    """A device/session entry. Carries no token material."""

    id: UUID = Field(description="Session identifier")
    user_agent: str | None = Field(default=None, description="Client user agent at creation")
    ip_address: str | None = Field(default=None, description="Client address at creation")
    active_tenant_id: UUID | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime
    is_current: bool = Field(
        default=False, description="Whether this is the session making the request"
    )

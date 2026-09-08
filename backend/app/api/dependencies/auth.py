"""Authentication dependencies.

Resolves the bearer token into a ``Principal``: a validated user plus the
claims of the token that identified them. Deliberately does **not** grant any
tenant access — the token's ``tid`` claim is only a candidate here, and is
re-validated against ``tenant_memberships`` by
:mod:`app.api.dependencies.tenant` on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies.core import ResourcesDep
from app.api.dependencies.db import UnscopedSessionDep
from app.config.logging import get_logger
from app.core.context import set_user_id
from app.core.exceptions import AuthenticationError, InactiveUserError, InvalidTokenError
from app.core.security.jwt import AccessTokenClaims
from app.models.users import User
from app.repositories.sessions import RefreshSessionRepository
from app.repositories.users import UserRepository

logger = get_logger(__name__)

#: ``auto_error=False`` so a missing header becomes our own 401 envelope
#: rather than FastAPI's ``{"detail": ...}`` shape.
bearer_scheme = HTTPBearer(
    scheme_name="Bearer",
    description="JWT access token issued by /api/v1/auth/login",
    auto_error=False,
)


@dataclass(slots=True)
class Principal:
    """The authenticated caller."""

    user: User
    claims: AccessTokenClaims

    @property
    def user_id(self) -> UUID:
        return self.user.id

    @property
    def session_id(self) -> UUID:
        return self.claims.session_id

    @property
    def claimed_tenant_id(self) -> UUID | None:
        """Workspace the token claims. A *candidate*, never an authorisation."""
        return self.claims.tenant_id


async def get_principal(
    request: Request,
    resources: ResourcesDep,
    session: UnscopedSessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """Validate the access token and load the user.

    Checks, in order: the header is present and well-formed; the token's
    signature, lifetime, issuer, audience and type are valid; the session it
    was issued against has not been revoked; and the user is still active.

    The session check is what makes logout meaningful for access tokens too:
    without it, a revoked refresh token would still leave a valid access token
    working until it expired.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("An Authorization: Bearer <token> header is required")
    if credentials.scheme.lower() != "bearer":
        raise InvalidTokenError("Authorization scheme must be Bearer")

    claims = resources.jwt_service.decode_access_token(credentials.credentials)

    sessions = RefreshSessionRepository(session)
    session_row = await sessions.get_by_id_for_user(claims.session_id, claims.user_id)
    if session_row is None or session_row.revoked:
        logger.info(
            "access token rejected: session revoked or unknown",
            extra={"user_id": str(claims.user_id)},
        )
        raise AuthenticationError("Session is no longer valid", code="SESSION_REVOKED")

    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None:
        # A token for a deleted account. Same message as any other auth failure.
        raise AuthenticationError()
    if not user.is_active:
        raise InactiveUserError()

    # Bind for logging and audit, so every later record carries the actor.
    set_user_id(user.id)
    request.state.principal = Principal(user=user, claims=claims)
    return request.state.principal  # type: ignore[no-any-return]


PrincipalDep = Annotated[Principal, Depends(get_principal)]

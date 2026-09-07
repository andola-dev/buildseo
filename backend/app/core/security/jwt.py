"""JSON Web Token issuing and validation for access tokens.

Only *access* tokens are JWTs; refresh tokens are opaque
(:mod:`app.core.security.refresh_tokens`). The claim set is deliberately small:
identity plus the currently selected tenant. It is never treated as an
authorisation cache — ``tid`` is re-validated against ``tenant_memberships`` on
every request, and permissions are always loaded from the database, so a stale
or forged claim cannot grant access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError
from jwt import InvalidTokenError as PyJwtInvalidTokenError

from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.ids import uuid7

ACCESS_TOKEN_TYPE: Final = "access"  # noqa: S105 - a claim discriminator, not a secret
_REQUIRED_CLAIMS: Final = ["exp", "iat", "nbf", "sub", "jti", "typ", "iss", "aud"]


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Validated claims of an access token."""

    user_id: UUID
    session_id: UUID
    token_id: UUID
    tenant_id: UUID | None
    issued_at: datetime
    expires_at: datetime

    @property
    def has_tenant(self) -> bool:
        return self.tenant_id is not None


class JwtService:
    """Encodes and decodes access tokens with a pinned algorithm."""

    __slots__ = ("_algorithm", "_audience", "_issuer", "_leeway", "_secret", "_ttl")

    def __init__(
        self,
        *,
        secret: str,
        algorithm: str = "HS256",
        issuer: str = "buildseo",
        audience: str = "buildseo-api",
        access_token_ttl: timedelta = timedelta(minutes=15),
        leeway_seconds: int = 10,
    ) -> None:
        if not secret or len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        if algorithm not in ("HS256", "HS384", "HS512"):
            raise ValueError(f"unsupported JWT algorithm: {algorithm}")
        self._secret = secret
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._ttl = access_token_ttl
        self._leeway = leeway_seconds

    @property
    def access_token_ttl(self) -> timedelta:
        return self._ttl

    def create_access_token(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        tenant_id: UUID | None = None,
        issued_at: datetime | None = None,
    ) -> tuple[str, AccessTokenClaims]:
        """Mint an access token and return it with its decoded claims."""
        now = (issued_at or datetime.now(UTC)).replace(microsecond=0)
        expires_at = now + self._ttl
        token_id = uuid7()

        payload: dict[str, Any] = {
            "sub": str(user_id),
            "jti": str(token_id),
            "sid": str(session_id),
            "typ": ACCESS_TOKEN_TYPE,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if tenant_id is not None:
            payload["tid"] = str(tenant_id)

        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        claims = AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            token_id=token_id,
            tenant_id=tenant_id,
            issued_at=now,
            expires_at=expires_at,
        )
        return token, claims

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Validate signature, lifetime, issuer, audience and token type.

        The algorithm is pinned to the configured one, so a token whose header
        claims ``alg: none`` or a different family is rejected outright rather
        than dispatched on attacker-controlled input.
        """
        if not token:
            raise InvalidTokenError("Access token is missing")
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": _REQUIRED_CLAIMS, "verify_signature": True},
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError() from exc
        except PyJwtInvalidTokenError as exc:
            raise InvalidTokenError() from exc

        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("Token is not an access token")

        try:
            user_id = UUID(payload["sub"])
            session_id = UUID(payload["sid"])
            token_id = UUID(payload["jti"])
            raw_tenant = payload.get("tid")
            tenant_id = UUID(raw_tenant) if raw_tenant else None
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidTokenError("Token claims are malformed") from exc

        return AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            token_id=token_id,
            tenant_id=tenant_id,
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )

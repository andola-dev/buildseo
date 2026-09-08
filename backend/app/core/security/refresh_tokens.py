"""Opaque refresh tokens.

Refresh tokens are **not** JWTs. Revocation has to be authoritative, and an
opaque random string that is worthless without its database row gives that for
free: there is nothing to verify offline, so a stolen token stops working the
instant its row is revoked.

Only a SHA-256 digest is ever persisted. SHA-256 (rather than a slow KDF) is
correct here because the token is 256 bits of ``secrets``-grade entropy — there
is no low-entropy guess space for an attacker to search, so the only property
needed is a fast, collision-resistant one-way mapping.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from uuid import UUID

#: 32 bytes → 43 URL-safe base64 characters, 256 bits of entropy.
TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """A freshly minted token: the plaintext for the client, the hash for the DB."""

    token: str
    token_hash: str
    family_id: UUID

    def __repr__(self) -> str:
        """Redacted so the raw token cannot reach a log line."""
        return f"IssuedRefreshToken(family_id={self.family_id}, token=<redacted>)"


def generate_refresh_token() -> str:
    """Return a cryptographically random, URL-safe refresh token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Return the hex SHA-256 digest stored in ``refresh_sessions.token_hash``."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_matches(token: str, token_hash: str) -> bool:
    """Constant-time comparison of a presented token against a stored digest."""
    return hmac.compare_digest(hash_refresh_token(token), token_hash)

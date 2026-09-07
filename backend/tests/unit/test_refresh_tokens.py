"""Opaque refresh tokens.

Refresh tokens are not JWTs: revocation has to be authoritative, so the token
is meaningless without its database row and only a digest is ever stored.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security.refresh_tokens import (
    TOKEN_BYTES,
    IssuedRefreshToken,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_matches,
)

pytestmark = pytest.mark.unit


class TestGeneration:
    def test_tokens_are_unique(self) -> None:
        tokens = {generate_refresh_token() for _ in range(500)}
        assert len(tokens) == 500

    def test_tokens_carry_the_intended_entropy(self) -> None:
        # 32 bytes of urlsafe base64 is 43 characters.
        assert TOKEN_BYTES == 32
        assert len(generate_refresh_token()) >= 43

    def test_tokens_are_url_safe(self) -> None:
        token = generate_refresh_token()
        assert all(char.isalnum() or char in "-_" for char in token)


class TestHashing:
    def test_hashing_is_deterministic(self) -> None:
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_digest_is_a_sha256_hex_string(self) -> None:
        assert len(hash_refresh_token(generate_refresh_token())) == 64

    def test_different_tokens_hash_differently(self) -> None:
        assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
            generate_refresh_token()
        )

    def test_the_stored_digest_does_not_contain_the_token(self) -> None:
        token = generate_refresh_token()
        assert token not in hash_refresh_token(token)


class TestComparison:
    def test_matches_the_right_token(self) -> None:
        token = generate_refresh_token()
        assert refresh_token_matches(token, hash_refresh_token(token))

    def test_rejects_a_different_token(self) -> None:
        assert not refresh_token_matches(
            generate_refresh_token(), hash_refresh_token(generate_refresh_token())
        )

    def test_rejects_a_malformed_digest(self) -> None:
        assert not refresh_token_matches(generate_refresh_token(), "not-a-digest")


class TestIssuedTokenRepr:
    def test_repr_never_prints_the_token(self) -> None:
        token = generate_refresh_token()
        issued = IssuedRefreshToken(
            token=token, token_hash=hash_refresh_token(token), family_id=uuid4()
        )
        assert token not in repr(issued)
        assert "redacted" in repr(issued)

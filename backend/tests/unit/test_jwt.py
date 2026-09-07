"""Access-token issuing and validation.

Requires PyJWT, so this module lives with the other unit tests but does not
run without the full dependency set installed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security.jwt import ACCESS_TOKEN_TYPE, JwtService

pytestmark = pytest.mark.unit

SECRET = "a" * 48
OTHER_SECRET = "b" * 48


@pytest.fixture
def service() -> JwtService:
    return JwtService(secret=SECRET, issuer="buildseo", audience="buildseo-api")


class TestConstruction:
    def test_rejects_a_short_secret(self) -> None:
        with pytest.raises(ValueError, match="32 characters"):
            JwtService(secret="too-short")

    def test_rejects_an_unsupported_algorithm(self) -> None:
        # Pinning the algorithm family is what prevents algorithm confusion.
        with pytest.raises(ValueError, match="algorithm"):
            JwtService(secret=SECRET, algorithm="RS256")


class TestRoundTrip:
    def test_issues_and_validates_a_token(self, service: JwtService) -> None:
        user_id, session_id, tenant_id = uuid4(), uuid4(), uuid4()
        token, claims = service.create_access_token(
            user_id=user_id, session_id=session_id, tenant_id=tenant_id
        )

        decoded = service.decode_access_token(token)
        assert decoded.user_id == user_id
        assert decoded.session_id == session_id
        assert decoded.tenant_id == tenant_id
        assert decoded.token_id == claims.token_id
        assert decoded.has_tenant

    def test_a_token_without_a_workspace_is_valid(self, service: JwtService) -> None:
        # A user who belongs to several workspaces gets one of these until they
        # select a workspace.
        token, _ = service.create_access_token(user_id=uuid4(), session_id=uuid4())
        decoded = service.decode_access_token(token)
        assert decoded.tenant_id is None
        assert not decoded.has_tenant

    def test_each_token_has_a_unique_identifier(self, service: JwtService) -> None:
        user_id, session_id = uuid4(), uuid4()
        first, _ = service.create_access_token(user_id=user_id, session_id=session_id)
        second, _ = service.create_access_token(user_id=user_id, session_id=session_id)
        assert (
            service.decode_access_token(first).token_id
            != service.decode_access_token(second).token_id
        )

    def test_expiry_follows_the_configured_lifetime(self) -> None:
        service = JwtService(secret=SECRET, access_token_ttl=timedelta(minutes=15))
        _, claims = service.create_access_token(user_id=uuid4(), session_id=uuid4())
        assert claims.expires_at - claims.issued_at == timedelta(minutes=15)


class TestRejections:
    def test_rejects_an_empty_token(self, service: JwtService) -> None:
        with pytest.raises(InvalidTokenError):
            service.decode_access_token("")

    def test_rejects_a_malformed_token(self, service: JwtService) -> None:
        with pytest.raises(InvalidTokenError):
            service.decode_access_token("not.a.jwt")

    def test_rejects_a_token_signed_with_another_key(self, service: JwtService) -> None:
        forger = JwtService(secret=OTHER_SECRET, issuer="buildseo", audience="buildseo-api")
        token, _ = forger.create_access_token(user_id=uuid4(), session_id=uuid4())
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(token)

    def test_rejects_an_expired_token(self) -> None:
        service = JwtService(
            secret=SECRET, access_token_ttl=timedelta(minutes=15), leeway_seconds=0
        )
        token, _ = service.create_access_token(
            user_id=uuid4(),
            session_id=uuid4(),
            issued_at=datetime.now(UTC) - timedelta(hours=2),
        )
        with pytest.raises(TokenExpiredError):
            service.decode_access_token(token)

    def test_rejects_a_token_for_another_audience(self, service: JwtService) -> None:
        other = JwtService(secret=SECRET, issuer="buildseo", audience="someone-else")
        token, _ = other.create_access_token(user_id=uuid4(), session_id=uuid4())
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(token)

    def test_rejects_a_token_from_another_issuer(self, service: JwtService) -> None:
        other = JwtService(secret=SECRET, issuer="somewhere-else", audience="buildseo-api")
        token, _ = other.create_access_token(user_id=uuid4(), session_id=uuid4())
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(token)

    def test_rejects_an_unsigned_token(self, service: JwtService) -> None:
        # Algorithm confusion: alg=none must never be accepted.
        import jwt as pyjwt

        forged = pyjwt.encode(
            {
                "sub": str(uuid4()),
                "sid": str(uuid4()),
                "jti": str(uuid4()),
                "typ": ACCESS_TOKEN_TYPE,
                "iss": "buildseo",
                "aud": "buildseo-api",
                "iat": int(datetime.now(UTC).timestamp()),
                "nbf": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            key="",
            algorithm="none",
        )
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(forged)

    def test_rejects_a_token_of_the_wrong_type(self, service: JwtService) -> None:
        import jwt as pyjwt

        now = datetime.now(UTC)
        forged = pyjwt.encode(
            {
                "sub": str(uuid4()),
                "sid": str(uuid4()),
                "jti": str(uuid4()),
                "typ": "refresh",
                "iss": "buildseo",
                "aud": "buildseo-api",
                "iat": int(now.timestamp()),
                "nbf": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            key=SECRET,
            algorithm="HS256",
        )
        with pytest.raises(InvalidTokenError, match="not an access token"):
            service.decode_access_token(forged)

    @pytest.mark.parametrize("missing", ["sub", "sid", "jti", "exp", "iat", "nbf"])
    def test_rejects_a_token_missing_a_required_claim(
        self, service: JwtService, missing: str
    ) -> None:
        import jwt as pyjwt

        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "sid": str(uuid4()),
            "jti": str(uuid4()),
            "typ": ACCESS_TOKEN_TYPE,
            "iss": "buildseo",
            "aud": "buildseo-api",
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        del payload[missing]
        forged = pyjwt.encode(payload, key=SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(forged)

    def test_rejects_malformed_claim_values(self, service: JwtService) -> None:
        import jwt as pyjwt

        now = datetime.now(UTC)
        forged = pyjwt.encode(
            {
                "sub": "not-a-uuid",
                "sid": str(uuid4()),
                "jti": str(uuid4()),
                "typ": ACCESS_TOKEN_TYPE,
                "iss": "buildseo",
                "aud": "buildseo-api",
                "iat": int(now.timestamp()),
                "nbf": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            key=SECRET,
            algorithm="HS256",
        )
        with pytest.raises(InvalidTokenError, match="malformed"):
            service.decode_access_token(forged)

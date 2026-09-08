"""Token lifecycle security over HTTP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security.jwt import JwtService
from app.core.security.refresh_tokens import hash_refresh_token
from app.db.session import TenantAwareSession
from tests.fixtures.api import auth_headers, login
from tests.fixtures.tenants import PASSWORD, TenantFixture

pytestmark = [pytest.mark.security, pytest.mark.api]


class TestNoUserEnumeration:
    async def test_an_unknown_email_and_a_wrong_password_are_indistinguishable(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        unknown = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@fixture.example.com", "password": PASSWORD},
        )
        wrong = await client.post(
            "/api/v1/auth/login",
            json={"email": tenant_a.owner.email, "password": "Wrong!Password123"},
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


class TestRefreshRotation:
    async def test_refreshing_issues_a_new_pair(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 200
        rotated = response.json()["data"]
        assert rotated["refresh_token"] != tokens["refresh_token"]
        assert rotated["access_token"] != tokens["access_token"]

    async def test_the_old_token_stops_working_after_rotation(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "TOKEN_REVOKED"

    async def test_replaying_a_rotated_token_kills_the_whole_family(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        # Replay means the token leaked, so every descendant of that login is
        # revoked — not just the replayed row.
        first = await login(client, email=tenant_a.owner.email)
        second = (
            await client.post(
                "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
            )
        ).json()["data"]

        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert replay.status_code == 401

        # The token that was legitimately issued is now dead too.
        after = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
        )
        assert after.status_code == 401

    async def test_an_unknown_refresh_token_is_rejected(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN"

    async def test_an_expired_refresh_token_is_rejected(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        session_factory: async_sessionmaker[TenantAwareSession],
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        async with session_factory() as session:
            await session.execute(
                text("UPDATE refresh_sessions SET expires_at = :past WHERE token_hash = :hash"),
                {
                    "past": datetime.now(UTC) - timedelta(days=1),
                    "hash": hash_refresh_token(tokens["refresh_token"]),
                },
            )
            await session.commit()

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


class TestTokenStorage:
    async def test_only_a_digest_of_the_refresh_token_is_stored(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        session_factory: async_sessionmaker[TenantAwareSession],
    ) -> None:
        # A dump of refresh_sessions must not be replayable against the API.
        tokens = await login(client, email=tenant_a.owner.email)
        async with session_factory() as session:
            rows = (
                (await session.execute(text("SELECT token_hash FROM refresh_sessions")))
                .scalars()
                .all()
            )
        assert tokens["refresh_token"] not in rows
        assert hash_refresh_token(tokens["refresh_token"]) in rows


class TestLogout:
    async def test_logout_invalidates_the_access_token_too(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        # The access token is checked against its session, so revoking the
        # session applies immediately rather than at token expiry.
        tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
        headers = auth_headers(tokens)
        assert (await client.get("/api/v1/me", headers=headers)).status_code == 200

        logged_out = await client.post(
            "/api/v1/auth/logout",
            headers=headers,
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert logged_out.status_code == 200

        after = await client.get("/api/v1/me", headers=headers)
        assert after.status_code == 401
        assert after.json()["error"]["code"] == "SESSION_REVOKED"

    async def test_logging_out_an_unknown_token_succeeds_without_confirming_it(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers(tokens),
            json={"refresh_token": "someone-elses-token"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["revoked_sessions"] == 0

    async def test_logout_everywhere_revokes_every_session(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        first = await login(client, email=tenant_a.owner.email)
        second = await login(client, email=tenant_a.owner.email)

        await client.post(
            "/api/v1/auth/logout", headers=auth_headers(first), json={"all_sessions": True}
        )
        assert (await client.get("/api/v1/me", headers=auth_headers(second))).status_code == 401


class TestAccessTokenValidation:
    @pytest.mark.parametrize(
        "header",
        [
            {},
            {"Authorization": "Bearer "},
            {"Authorization": "Bearer not.a.jwt"},
            {"Authorization": "Basic dXNlcjpwYXNz"},
        ],
    )
    async def test_a_missing_or_malformed_header_is_rejected(
        self, client: httpx.AsyncClient, header: dict
    ) -> None:
        response = await client.get("/api/v1/me", headers=header)
        assert response.status_code == 401
        assert "error" in response.json()

    async def test_a_token_signed_with_another_key_is_rejected(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        forger = JwtService(secret="f" * 48, issuer="buildseo", audience="buildseo-api")
        token, _ = forger.create_access_token(
            user_id=tenant_a.owner.id,
            session_id=tenant_a.owner.id,
            tenant_id=tenant_a.tenant_id,
        )
        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_an_expired_access_token_is_rejected(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, settings
    ) -> None:
        service = JwtService(
            secret=settings.jwt_secret.get_secret_value(),
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            access_token_ttl=timedelta(minutes=15),
            leeway_seconds=0,
        )
        token, _ = service.create_access_token(
            user_id=tenant_a.owner.id,
            session_id=tenant_a.owner.id,
            tenant_id=tenant_a.tenant_id,
            issued_at=datetime.now(UTC) - timedelta(hours=2),
        )
        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "TOKEN_EXPIRED"

    async def test_a_forged_tenant_claim_buys_nothing(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        settings,
    ) -> None:
        """The token's tid is a candidate, not an authorisation.

        A validly-signed token naming a workspace the user does not belong to
        must be refused, because membership is re-checked on every request.
        """
        tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
        service = JwtService(
            secret=settings.jwt_secret.get_secret_value(),
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
        claims = service.decode_access_token(tokens["access_token"])
        forged, _ = service.create_access_token(
            user_id=claims.user_id,
            session_id=claims.session_id,
            tenant_id=tenant_b.tenant_id,  # a workspace this user cannot enter
        )
        response = await client.get(
            "/api/v1/publishers", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    async def test_a_forged_tenant_header_buys_nothing(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, tenant_b: TenantFixture
    ) -> None:
        response = await client.get(
            "/api/v1/publishers",
            headers={**tenant_a_headers, "X-Tenant-ID": str(tenant_b.tenant_id)},
        )
        assert response.status_code == 403


class TestPasswordChange:
    async def test_changing_a_password_requires_the_current_one(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # A stolen access token must not be enough to take over the account.
        response = await client.post(
            "/api/v1/me/password",
            headers=tenant_a_headers,
            json={"current_password": "Wrong!Password123", "new_password": "N3w!Password456"},
        )
        assert response.status_code == 401

    async def test_a_successful_change_signs_out_other_devices(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        other_device = await login(client, email=tenant_a.owner.email)
        current = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)

        response = await client.post(
            "/api/v1/me/password",
            headers=auth_headers(current),
            json={"current_password": PASSWORD, "new_password": "N3w!Password456"},
        )
        assert response.status_code == 200

        # The other device is out; the caller keeps working.
        assert (
            await client.get("/api/v1/me", headers=auth_headers(other_device))
        ).status_code == 401
        assert (await client.get("/api/v1/me", headers=auth_headers(current))).status_code == 200

    async def test_the_new_password_must_differ_and_be_strong(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        same = await client.post(
            "/api/v1/me/password",
            headers=tenant_a_headers,
            json={"current_password": PASSWORD, "new_password": PASSWORD},
        )
        assert same.status_code == 422
        assert same.json()["error"]["code"] == "PASSWORD_UNCHANGED"

        weak = await client.post(
            "/api/v1/me/password",
            headers=tenant_a_headers,
            json={"current_password": PASSWORD, "new_password": "password"},
        )
        assert weak.status_code == 422

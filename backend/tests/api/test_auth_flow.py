"""End-to-end authentication and workspace selection."""

from __future__ import annotations

import httpx
import pytest

from tests.fixtures.api import auth_headers, login
from tests.fixtures.tenants import PASSWORD, TenantFixture

pytestmark = pytest.mark.api


class TestRegistration:
    async def test_registering_with_a_workspace_returns_a_scoped_token(
        self, client: httpx.AsyncClient, seeded_permissions: None
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "founder@newco.test",
                "password": "F0under!Password",
                "first_name": "Sam",
                "tenant_name": "NewCo",
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["active_tenant_id"] is not None
        assert data["token_type"] == "bearer"

    async def test_the_new_owner_gets_the_owner_role_and_every_permission(
        self, client: httpx.AsyncClient, seeded_permissions: None
    ) -> None:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "founder2@newco.test",
                "password": "F0under!Password",
                "tenant_name": "NewCo Two",
            },
        )
        headers = auth_headers(registered.json()["data"])
        me = await client.get("/api/v1/me", headers=headers)
        body = me.json()["data"]
        assert body["tenants"][0]["is_owner"] is True
        assert body["tenants"][0]["roles"] == ["owner"]
        assert "tenant.delete" in body["permissions"]

    async def test_registering_without_a_workspace_yields_an_unscoped_token(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "solo@newco.test", "password": "S0lo!Password123"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["active_tenant_id"] is None

    async def test_a_duplicate_email_is_a_conflict(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": tenant_a.owner.email, "password": "An0ther!Password"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    async def test_email_uniqueness_is_case_insensitive(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": tenant_a.owner.email.upper(), "password": "An0ther!Password"},
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "password", ["short", "alllowercase1!", "Password123!", "NoDigitsHere!!"]
    )
    async def test_a_weak_password_is_rejected_with_the_requirements(
        self, client: httpx.AsyncClient, password: str
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": f"weak-{len(password)}@newco.test", "password": password},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestLogin:
    async def test_logging_in_returns_a_usable_token(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
        me = await client.get("/api/v1/me", headers=auth_headers(tokens))
        assert me.status_code == 200
        assert me.json()["data"]["user"]["email"] == tenant_a.owner.email

    async def test_a_sole_workspace_is_selected_automatically(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        # Convenient, and safe because it is the user's own membership.
        tokens = await login(client, email=tenant_a.owner.email)
        assert tokens["active_tenant_id"] == str(tenant_a.tenant_id)

    async def test_requesting_a_workspace_the_user_cannot_enter_is_refused(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_b: TenantFixture
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": tenant_a.owner.email,
                "password": PASSWORD,
                "tenant_id": str(tenant_b.tenant_id),
            },
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    async def test_the_user_response_never_contains_a_password_hash(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/me", headers=tenant_a_headers)
        assert "password" not in response.text.lower()


class TestWorkspaceSelectionAndSwitching:
    async def test_a_user_in_two_workspaces_must_choose(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        tenant_a_headers: dict,
        tenant_b_headers: dict,
    ) -> None:
        # Add tenant A's owner to tenant B as well.
        added = await client.post(
            f"/api/v1/tenants/{tenant_b.tenant_id}/members",
            headers=tenant_b_headers,
            json={"email": tenant_a.owner.email, "role_slugs": ["viewer"]},
        )
        assert added.status_code == 201, added.text

        tokens = await login(client, email=tenant_a.owner.email)
        # Two memberships, so no workspace is chosen implicitly.
        assert tokens["active_tenant_id"] is None

        needs_tenant = await client.get("/api/v1/publishers", headers=auth_headers(tokens))
        assert needs_tenant.status_code == 400
        assert needs_tenant.json()["error"]["code"] == "TENANT_CONTEXT_REQUIRED"

    async def test_selecting_a_workspace_issues_a_scoped_access_token(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        tenant_b_headers: dict,
    ) -> None:
        await client.post(
            f"/api/v1/tenants/{tenant_b.tenant_id}/members",
            headers=tenant_b_headers,
            json={"email": tenant_a.owner.email, "role_slugs": ["viewer"]},
        )
        tokens = await login(client, email=tenant_a.owner.email)

        selected = await client.post(
            "/api/v1/auth/select-tenant",
            headers=auth_headers(tokens),
            json={"tenant_id": str(tenant_b.tenant_id)},
        )
        assert selected.status_code == 200
        data = selected.json()["data"]
        assert data["active_tenant_id"] == str(tenant_b.tenant_id)
        # Switching workspace is not a re-authentication, so no refresh token
        # is reissued.
        assert "refresh_token" not in data

        scoped = auth_headers(data)
        publishers = await client.get("/api/v1/publishers", headers=scoped)
        assert publishers.status_code == 200
        domains = {row["normalized_domain"] for row in publishers.json()["data"]}
        assert domains == {"tenant-b-freedir.test", "tenant-b-paiddir.test"}

    async def test_selecting_a_workspace_the_user_cannot_enter_is_refused(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_b: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.post(
            "/api/v1/auth/select-tenant",
            headers=auth_headers(tokens),
            json={"tenant_id": str(tenant_b.tenant_id)},
        )
        assert response.status_code == 403

    async def test_the_tenant_header_can_switch_workspace_per_request(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        tenant_b_headers: dict,
    ) -> None:
        await client.post(
            f"/api/v1/tenants/{tenant_b.tenant_id}/members",
            headers=tenant_b_headers,
            json={"email": tenant_a.owner.email, "role_slugs": ["viewer"]},
        )
        tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
        response = await client.get(
            "/api/v1/publishers",
            headers={**auth_headers(tokens), "X-Tenant-ID": str(tenant_b.tenant_id)},
        )
        assert response.status_code == 200
        domains = {row["normalized_domain"] for row in response.json()["data"]}
        assert domains == {"tenant-b-freedir.test", "tenant-b-paiddir.test"}


class TestSessions:
    async def test_sessions_are_listed_without_token_material(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/auth/sessions", headers=tenant_a_headers)
        assert response.status_code == 200
        rows = response.json()["data"]
        assert rows
        assert any(row["is_current"] for row in rows)
        for row in rows:
            assert "token" not in row
            assert "token_hash" not in row

    async def test_revoking_a_session_signs_that_device_out(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        other = await login(client, email=tenant_a.owner.email)
        current = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)

        sessions = await client.get("/api/v1/auth/sessions", headers=auth_headers(current))
        target = next(row for row in sessions.json()["data"] if not row["is_current"])
        revoked = await client.delete(
            f"/api/v1/auth/sessions/{target['id']}", headers=auth_headers(current)
        )
        assert revoked.status_code == 200

        assert (await client.get("/api/v1/me", headers=auth_headers(other))).status_code == 401
        assert (await client.get("/api/v1/me", headers=auth_headers(current))).status_code == 200

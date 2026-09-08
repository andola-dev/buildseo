"""Bootstrap: getting from "logged in" to "acting in a workspace".

Every test here failed before the fix it guards, and each one failed for the
same underlying reason: ``tenant_memberships`` is itself RLS-protected, and the
policy that lets a member see their *own* rows tests ``app_current_user_id()``.
Reads that decide which workspace to enter necessarily run before any tenant is
known, so unless the principal is bound first they return nothing — and the API
then reports a legitimate owner as a non-member.

The failure mode was a hard deadlock: a caller could not select a workspace
because they could not list their workspaces, and could not list them because
no workspace was selected.

**These tests only mean anything when the app runs as the ``NOBYPASSRLS``
runtime role.** ``tests/fixtures/database.py::resources`` is bound to
``rls_engine`` for exactly this reason: on the owner engine — a SUPERUSER,
which bypasses RLS entirely — every assertion below passes whether the bug is
present or not.
"""

from __future__ import annotations

import httpx
import pytest

from tests.fixtures.api import auth_headers, login
from tests.fixtures.tenants import PASSWORD, TenantFixture

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestBootstrapEndToEnd:
    async def test_a_member_can_reach_their_workspace_from_a_plain_login(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        """The whole path, in the order a client actually walks it.

        This single test covers the three blocking symptoms: every
        tenant-scoped endpoint returning 403, ``/auth/select-tenant`` refusing
        a valid membership, and ``/me`` reporting no workspaces at all.
        """
        tokens = await login(client, email=tenant_a.owner.email)
        headers = auth_headers(tokens)

        # 1. The workspace is discoverable.
        me = await client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        listed = {tenant["tenant_id"] for tenant in me.json()["data"]["tenants"]}
        assert str(tenant_a.tenant_id) in listed

        # 2. It can be selected — the only path that mints a tid-bearing token.
        selected = await client.post(
            "/api/v1/auth/select-tenant",
            json={"tenant_id": str(tenant_a.tenant_id)},
            headers=headers,
        )
        assert selected.status_code == 200
        assert selected.json()["data"]["active_tenant_id"] == str(tenant_a.tenant_id)
        scoped = auth_headers(selected.json()["data"])

        # 3. And tenant-scoped reads work with the resulting token.
        for path in (
            "/api/v1/campaigns",
            "/api/v1/client-websites",
            "/api/v1/publishers",
            "/api/v1/opportunities",
            "/api/v1/submissions",
            "/api/v1/credentials",
            "/api/v1/roles",
            "/api/v1/permissions",
            "/api/v1/audit-logs",
        ):
            response = await client.get(path, headers=scoped)
            assert response.status_code == 200, f"{path} -> {response.status_code}"

    async def test_my_workspaces_are_listed(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.get("/api/v1/me/tenants", headers=auth_headers(tokens))
        assert response.status_code == 200
        assert response.json()["meta"]["total"] >= 1
        assert str(tenant_a.tenant_id) in {row["id"] for row in response.json()["data"]}

    async def test_only_my_own_workspaces_are_listed(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """The self-read policy must not turn into "read every membership"."""
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.get("/api/v1/me/tenants", headers=auth_headers(tokens))
        assert str(tenant_b.tenant_id) not in {row["id"] for row in response.json()["data"]}

    async def test_permissions_are_reported_for_the_active_workspace(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        """An owner with an empty permission set renders a UI with nothing in it."""
        tokens = await login(client, email=tenant_a.owner.email)
        me = await client.get("/api/v1/me", headers=auth_headers(tokens))
        body = me.json()["data"]
        assert body["active_tenant_id"] == str(tenant_a.tenant_id)
        assert "tenant.read" in body["permissions"]


class TestCreateThenSelect:
    async def test_a_new_workspace_is_immediately_discoverable(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        """Creation that cannot be followed by selection is a dead end.

        For a user with no workspace this is the only self-service escape
        hatch, so it has to work end to end rather than merely return 201.
        """
        tokens = await login(client, email=tenant_a.owner.email)
        headers = auth_headers(tokens)

        created = await client.post(
            "/api/v1/tenants", json={"name": "Second Workspace"}, headers=headers
        )
        assert created.status_code == 201
        new_id = created.json()["data"]["id"]

        listed = await client.get("/api/v1/me/tenants", headers=headers)
        assert new_id in {row["id"] for row in listed.json()["data"]}

        selected = await client.post(
            "/api/v1/auth/select-tenant", json={"tenant_id": new_id}, headers=headers
        )
        assert selected.status_code == 200
        scoped = auth_headers(selected.json()["data"])

        # The seeded roles came with it, so the new owner can actually work.
        roles = await client.get("/api/v1/roles", headers=scoped)
        assert roles.status_code == 200
        assert {role["slug"] for role in roles.json()["data"]} >= {"owner", "admin", "viewer"}


class TestActiveTenantResolution:
    """``/me`` and every other endpoint must agree on the active workspace.

    The header is documented as authoritative and overriding the token claim.
    ``/me`` used to read the claim alone, so a client following that contract
    got ``active_tenant_id: null`` and an empty permission set from ``/me``
    while its data requests succeeded — and with permission-gated navigation
    that renders an application with every feature hidden.
    """

    async def test_the_header_is_honoured_like_the_token_claim(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email)
        headers = auth_headers(tokens)

        without = await client.get("/api/v1/me", headers=headers)
        with_header = await client.get(
            "/api/v1/me", headers={**headers, "X-Tenant-ID": str(tenant_a.tenant_id)}
        )
        assert with_header.status_code == 200
        assert with_header.json()["data"]["active_tenant_id"] == str(tenant_a.tenant_id)
        assert with_header.json()["data"]["permissions"] == without.json()["data"]["permissions"]

    async def test_a_workspace_the_caller_cannot_enter_reports_none(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """``/me`` degrades rather than refusing: it is the discovery endpoint.

        A client that asks for a workspace it cannot enter still needs to be
        told where it *can* go, so this is a 200 with no active workspace
        rather than the 403 a data endpoint would return.
        """
        tokens = await login(client, email=tenant_a.owner.email)
        response = await client.get(
            "/api/v1/me",
            headers={**auth_headers(tokens), "X-Tenant-ID": str(tenant_b.tenant_id)},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["active_tenant_id"] is None
        assert body["permissions"] == []
        # And no role names leak for a workspace the caller is not in.
        for tenant in body["tenants"]:
            if tenant["tenant_id"] == str(tenant_b.tenant_id):
                assert tenant["roles"] == []


class TestLoginTenantContract:
    async def test_an_owned_workspace_is_honoured(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
        assert tokens["active_tenant_id"] == str(tenant_a.tenant_id)

    async def test_an_unowned_workspace_is_rejected_not_silently_dropped(
        self,
        client: httpx.AsyncClient,
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """``LoginRequest.tenant_id`` promises validation, so it must refuse.

        Returning 200 with a different active workspace than the one asked for
        is the one outcome that should not happen: the caller has no way to
        tell it did not get what it requested.
        """
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


class TestRefreshKeepsTheWorkspace:
    async def test_a_refreshed_token_keeps_its_workspace_scope(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture
    ) -> None:
        """Re-validating membership on refresh must not fail for everyone.

        The check exists so a token cannot outlive the access it represents.
        Run without the principal bound it sees no membership at all, so every
        refresh silently de-scoped a perfectly good session — indistinguishable
        from a genuine revocation.
        """
        tokens = await login(client, email=tenant_a.owner.email)
        assert tokens["active_tenant_id"] == str(tenant_a.tenant_id)

        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["data"]["active_tenant_id"] == str(tenant_a.tenant_id)

        # And the refreshed token really works against a scoped endpoint.
        response = await client.get(
            "/api/v1/campaigns", headers=auth_headers(refreshed.json()["data"])
        )
        assert response.status_code == 200

"""Authorisation is enforced by permission, over HTTP.

These exercise the real dependency chain — token, membership, tenant context,
permission check — rather than the permission catalog in isolation.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.enums import MembershipStatus
from app.rbac.catalog import Perm
from tests.fixtures.api import auth_headers, login
from tests.fixtures.tenants import PASSWORD, TenantFixture

pytestmark = [pytest.mark.security, pytest.mark.api]


async def _member_with_role(
    client: httpx.AsyncClient,
    *,
    owner_headers: dict[str, str],
    tenant: TenantFixture,
    email: str,
    role_slug: str,
) -> dict[str, str]:
    """Register an account, add it to the workspace with one role, log it in."""
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "first_name": role_slug},
    )
    assert register.status_code == 201, register.text

    added = await client.post(
        f"/api/v1/tenants/{tenant.tenant_id}/members",
        headers=owner_headers,
        json={"email": email, "role_slugs": [role_slug], "status": MembershipStatus.ACTIVE.value},
    )
    assert added.status_code == 201, added.text

    tokens = await login(client, email=email, tenant_id=tenant.tenant_id)
    return auth_headers(tokens)


class TestViewerIsReadOnly:
    async def test_a_viewer_can_read_publishers(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="viewer@fixture.example.com",
            role_slug="viewer",
        )
        response = await client.get("/api/v1/publishers", headers=headers)
        assert response.status_code == 200

    async def test_a_viewer_cannot_create_a_publisher(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="viewer2@fixture.example.com",
            role_slug="viewer",
        )
        response = await client.post(
            "/api/v1/publishers",
            headers=headers,
            json={"website_url": "https://new-directory.test"},
        )
        assert response.status_code == 403
        body = response.json()["error"]
        assert body["code"] == "PERMISSION_DENIED"
        assert body["details"]["required_permission"] == Perm.PUBLISHER_CREATE.value

    async def test_a_viewer_cannot_read_credentials(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # Credentials and the audit trail are excluded from the Viewer role.
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="viewer3@fixture.example.com",
            role_slug="viewer",
        )
        assert (await client.get("/api/v1/credentials", headers=headers)).status_code == 403
        assert (await client.get("/api/v1/audit-logs", headers=headers)).status_code == 403


class TestSeparationOfDuties:
    async def test_a_specialist_can_prepare_but_not_approve_a_submission(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # The human-in-the-loop gate is a *different* permission from editing.
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="specialist@fixture.example.com",
            role_slug="seo_specialist",
        )

        created = await client.post(
            "/api/v1/submissions",
            headers=headers,
            json={
                "opportunity_id": str(tenant_a.opportunity.id),
                "submitted_title": "Client listing",
                "use_approved_content": False,
            },
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["data"]["id"]

        for_review = await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review", headers=headers
        )
        assert for_review.status_code == 200

        refused = await client.post(
            f"/api/v1/submissions/{submission_id}/approve", headers=headers, json={}
        )
        assert refused.status_code == 403
        assert (
            refused.json()["error"]["details"]["required_permission"]
            == Perm.SUBMISSION_APPROVE.value
        )

    async def test_a_manager_can_approve(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        manager = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="manager@fixture.example.com",
            role_slug="seo_manager",
        )
        created = await client.post(
            "/api/v1/submissions",
            headers=manager,
            json={
                "opportunity_id": str(tenant_a.opportunity.id),
                "submitted_title": "Client listing",
                "use_approved_content": False,
            },
        )
        submission_id = created.json()["data"]["id"]
        await client.post(f"/api/v1/submissions/{submission_id}/submit-for-review", headers=manager)
        approved = await client.post(
            f"/api/v1/submissions/{submission_id}/approve", headers=manager, json={}
        )
        assert approved.status_code == 200
        assert approved.json()["data"]["approved_by_user_id"] is not None

    async def test_a_specialist_cannot_administer_roles_or_members(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="specialist2@fixture.example.com",
            role_slug="seo_specialist",
        )
        create_role = await client.post(
            "/api/v1/roles",
            headers=headers,
            json={"slug": "sneaky", "name": "Sneaky", "permissions": ["tenant.read"]},
        )
        assert create_role.status_code == 403


class TestSuspendedMembership:
    async def test_a_suspended_member_loses_access_immediately(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # Permissions are resolved per request, so this takes effect on the
        # member's very next call rather than at token expiry.
        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="suspended@fixture.example.com",
            role_slug="seo_manager",
        )
        assert (await client.get("/api/v1/publishers", headers=headers)).status_code == 200

        members = await client.get(
            f"/api/v1/tenants/{tenant_a.tenant_id}/members", headers=tenant_a_headers
        )
        membership_id = next(
            row["id"]
            for row in members.json()["data"]
            if row["user"] and row["user"]["email"] == "suspended@fixture.example.com"
        )
        suspended = await client.patch(
            f"/api/v1/tenants/{tenant_a.tenant_id}/members/{membership_id}",
            headers=tenant_a_headers,
            json={"status": MembershipStatus.SUSPENDED.value},
        )
        assert suspended.status_code == 200

        after = await client.get("/api/v1/publishers", headers=headers)
        assert after.status_code == 403
        assert after.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


class TestSystemRolesAreProtected:
    async def test_a_system_role_cannot_be_edited(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        # A workspace that could strip permissions from its Owner role could
        # lock itself out.
        roles = await client.get("/api/v1/roles", headers=tenant_a_headers)
        owner_role = next(r for r in roles.json()["data"] if r["slug"] == "owner")
        response = await client.patch(
            f"/api/v1/roles/{owner_role['id']}",
            headers=tenant_a_headers,
            json={"permissions": ["tenant.read"]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SYSTEM_ROLE_IMMUTABLE"

    async def test_a_system_role_cannot_be_deleted(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        roles = await client.get("/api/v1/roles", headers=tenant_a_headers)
        viewer = next(r for r in roles.json()["data"] if r["slug"] == "viewer")
        response = await client.delete(f"/api/v1/roles/{viewer['id']}", headers=tenant_a_headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SYSTEM_ROLE_IMMUTABLE"


class TestCustomRoles:
    async def test_a_custom_role_grants_exactly_what_it_lists(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        created = await client.post(
            "/api/v1/roles",
            headers=tenant_a_headers,
            json={
                "slug": "publisher_researcher",
                "name": "Publisher Researcher",
                "permissions": [
                    Perm.PUBLISHER_READ.value,
                    Perm.PUBLISHER_CREATE.value,
                    Perm.TENANT_READ.value,
                ],
            },
        )
        assert created.status_code == 201, created.text

        headers = await _member_with_role(
            client,
            owner_headers=tenant_a_headers,
            tenant=tenant_a,
            email="researcher@fixture.example.com",
            role_slug="publisher_researcher",
        )
        assert (await client.get("/api/v1/publishers", headers=headers)).status_code == 200
        assert (await client.get("/api/v1/campaigns", headers=headers)).status_code == 403

    async def test_an_unknown_permission_code_is_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        # A role that looks like it grants something but does not is worse than
        # an error.
        response = await client.post(
            "/api/v1/roles",
            headers=tenant_a_headers,
            json={
                "slug": "bogus",
                "name": "Bogus",
                "permissions": ["publisher.publish"],
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNKNOWN_PERMISSION"

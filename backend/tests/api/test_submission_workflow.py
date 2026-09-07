"""The submission pipeline over HTTP, including the FREE-only rule."""

from __future__ import annotations

import httpx
import pytest

from app.core.enums import OpportunityStatus
from tests.fixtures.tenants import TenantFixture

pytestmark = pytest.mark.api


class TestFreeOnlyRule:
    """Business rules 1 and 2, enforced at every layer."""

    async def test_an_opportunity_cannot_be_created_for_a_paid_publisher(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # Refused at creation, so a paid publisher never reaches a work queue.
        response = await client.post(
            "/api/v1/opportunities",
            headers=tenant_a_headers,
            json={
                "campaign_id": str(tenant_a.campaign.id),
                "publisher_id": str(tenant_a.paid_publisher.id),
                "target_url": "https://tenant-a-client.test/",
            },
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "PAID_PLACEMENT_NOT_ALLOWED"
        assert error["details"]["pricing_type"] == "PAID"

    async def test_an_opportunity_can_be_created_for_a_free_publisher(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/opportunities",
            headers=tenant_a_headers,
            json={
                "campaign_id": str(tenant_a.campaign.id),
                "publisher_id": str(tenant_a.free_publisher.id),
                "target_url": "https://tenant-a-client.test/pricing",
            },
        )
        assert response.status_code == 201


class TestOpportunityIdempotency:
    async def test_repeating_a_create_returns_the_existing_row(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        payload = {
            "campaign_id": str(tenant_a.campaign.id),
            "publisher_id": str(tenant_a.free_publisher.id),
            "target_url": "https://tenant-a-client.test/about",
        }
        first = await client.post("/api/v1/opportunities", headers=tenant_a_headers, json=payload)
        assert first.status_code == 201
        assert first.json()["meta"]["created"] is True

        second = await client.post("/api/v1/opportunities", headers=tenant_a_headers, json=payload)
        # 200, not 409: a client that retried after a timeout gets the right
        # answer rather than an error.
        assert second.status_code == 200
        assert second.json()["meta"]["created"] is False
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

    async def test_an_idempotency_key_replays_the_original_response(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        payload = {
            "campaign_id": str(tenant_a.campaign.id),
            "publisher_id": str(tenant_a.free_publisher.id),
            "target_url": "https://tenant-a-client.test/contact",
        }
        headers = {**tenant_a_headers, "Idempotency-Key": "retry-key-1"}
        first = await client.post("/api/v1/opportunities", headers=headers, json=payload)
        second = await client.post("/api/v1/opportunities", headers=headers, json=payload)
        assert second.json()["data"]["id"] == first.json()["data"]["id"]
        assert second.json()["meta"].get("replayed") is True

    async def test_reusing_a_key_with_a_different_body_is_a_conflict(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # A client bug, and silently returning the earlier unrelated response
        # would hide it.
        headers = {**tenant_a_headers, "Idempotency-Key": "retry-key-2"}
        await client.post(
            "/api/v1/opportunities",
            headers=headers,
            json={
                "campaign_id": str(tenant_a.campaign.id),
                "publisher_id": str(tenant_a.free_publisher.id),
                "target_url": "https://tenant-a-client.test/a",
            },
        )
        conflicting = await client.post(
            "/api/v1/opportunities",
            headers=headers,
            json={
                "campaign_id": str(tenant_a.campaign.id),
                "publisher_id": str(tenant_a.free_publisher.id),
                "target_url": "https://tenant-a-client.test/b",
            },
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


class TestOpportunityLifecycle:
    async def test_qualification_inherits_the_publishers_judgement(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        created = await client.post(
            "/api/v1/opportunities",
            headers=tenant_a_headers,
            json={
                "campaign_id": str(tenant_a.campaign.id),
                "publisher_id": str(tenant_a.free_publisher.id),
                "target_url": "https://tenant-a-client.test/qualify",
            },
        )
        opportunity_id = created.json()["data"]["id"]
        qualified = await client.post(
            f"/api/v1/opportunities/{opportunity_id}/qualify", headers=tenant_a_headers
        )
        assert qualified.status_code == 200
        data = qualified.json()["data"]
        assert data["status"] == OpportunityStatus.QUALIFIED.value
        assert data["qualification_score"] is not None
        # Priority tracks the score by default.
        assert data["priority"] == round(float(data["qualification_score"]))

    async def test_an_illegal_transition_is_a_conflict(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            f"/api/v1/opportunities/{tenant_a.opportunity.id}/transition",
            headers=tenant_a_headers,
            json={"target_status": OpportunityStatus.PUBLISHED.value},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    async def test_rejecting_requires_a_reason_and_records_it(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            f"/api/v1/opportunities/{tenant_a.opportunity.id}/reject",
            headers=tenant_a_headers,
            json={"reason": "Directory is regional only"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == OpportunityStatus.REJECTED.value
        assert data["rejection_reason"] == "Directory is regional only"

    async def test_the_state_machine_is_published_for_clients(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/opportunities/state-machine", headers=tenant_a_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "QUALIFYING" in data["transitions"]["DISCOVERED"]
        assert data["transitions"]["PUBLISHED"] == []


class TestSubmissionWorkflow:
    async def _prepare(
        self, client: httpx.AsyncClient, tenant: TenantFixture, headers: dict
    ) -> str:
        response = await client.post(
            "/api/v1/submissions",
            headers=headers,
            json={
                "opportunity_id": str(tenant.opportunity.id),
                "submitted_title": "Tenant A client",
                "submitted_description": "A description of the business.",
                "use_approved_content": False,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["id"]

    async def test_a_new_submission_sends_nothing(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)
        fetched = await client.get(f"/api/v1/submissions/{submission_id}", headers=tenant_a_headers)
        data = fetched.json()["data"]
        assert data["status"] == "READY"
        assert data["submitted_at"] is None
        assert data["approved_by_user_id"] is None

    async def test_execution_without_approval_is_refused(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # The human-in-the-loop gate.
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)
        response = await client.post(
            f"/api/v1/submissions/{submission_id}/execute",
            headers=tenant_a_headers,
            json={},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "APPROVAL_REQUIRED"

    async def test_the_full_approved_path(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)

        for_review = await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review",
            headers=tenant_a_headers,
        )
        assert for_review.json()["data"]["status"] == "PENDING_APPROVAL"

        approved = await client.post(
            f"/api/v1/submissions/{submission_id}/approve",
            headers=tenant_a_headers,
            json={"notes": "Looks right"},
        )
        assert approved.json()["data"]["approved_by_user_id"] is not None

        executed = await client.post(
            f"/api/v1/submissions/{submission_id}/execute",
            headers=tenant_a_headers,
            json={"notes": "Submitted by hand"},
        )
        assert executed.status_code == 200
        data = executed.json()["data"]
        # Manual is the default, and it records rather than sends.
        assert data["submission_method"] == "MANUAL"
        assert data["submitted_at"] is not None
        assert data["status"] in ("SUBMITTED", "VERIFICATION_PENDING")

    async def test_editing_after_approval_clears_the_approval(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # Otherwise a reviewer's sign-off would apply to content they never saw.
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)
        await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review",
            headers=tenant_a_headers,
        )
        await client.post(
            f"/api/v1/submissions/{submission_id}/approve",
            headers=tenant_a_headers,
            json={},
        )
        edited = await client.patch(
            f"/api/v1/submissions/{submission_id}",
            headers=tenant_a_headers,
            json={"submitted_title": "A different title"},
        )
        data = edited.json()["data"]
        assert data["status"] == "IN_PROGRESS"
        assert data["approved_by_user_id"] is None

    async def test_only_one_live_submission_per_opportunity(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        await self._prepare(client, tenant_a, tenant_a_headers)
        second = await client.post(
            "/api/v1/submissions",
            headers=tenant_a_headers,
            json={
                "opportunity_id": str(tenant_a.opportunity.id),
                "submitted_title": "Duplicate",
                "use_approved_content": False,
            },
        )
        assert second.status_code == 422
        assert second.json()["error"]["code"] == "SUBMISSION_ALREADY_ACTIVE"

    async def test_a_submission_needs_a_title_before_review(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        created = await client.post(
            "/api/v1/submissions",
            headers=tenant_a_headers,
            json={
                "opportunity_id": str(tenant_a.opportunity.id),
                "use_approved_content": False,
            },
        )
        submission_id = created.json()["data"]["id"]
        response = await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review",
            headers=tenant_a_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SUBMISSION_CONTENT_MISSING"

    async def test_verification_can_record_a_human_finding(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)
        await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review",
            headers=tenant_a_headers,
        )
        await client.post(
            f"/api/v1/submissions/{submission_id}/approve",
            headers=tenant_a_headers,
            json={},
        )
        await client.post(
            f"/api/v1/submissions/{submission_id}/execute",
            headers=tenant_a_headers,
            json={"submitted_url": "https://tenant-a-freedir.test/listing/1"},
        )
        verified = await client.post(
            f"/api/v1/submissions/{submission_id}/verify",
            headers=tenant_a_headers,
            json={"fetch_live": False, "manual_result": True},
        )
        assert verified.status_code == 200
        data = verified.json()["data"]
        assert data["status"] == "VERIFIED"
        assert data["verified_at"] is not None
        assert data["verification_evidence"]["verification"]["manual"] is True

    async def test_the_review_queue_lists_submissions_awaiting_approval(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        submission_id = await self._prepare(client, tenant_a, tenant_a_headers)
        await client.post(
            f"/api/v1/submissions/{submission_id}/submit-for-review",
            headers=tenant_a_headers,
        )
        response = await client.get("/api/v1/submissions/review-queue", headers=tenant_a_headers)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["data"]] == [submission_id]

    async def test_the_state_machine_documents_the_approval_gate(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/submissions/state-machine", headers=tenant_a_headers)
        data = response.json()["data"]
        assert data["transitions"]["PENDING_APPROVAL"] == sorted(
            ["SUBMITTED", "IN_PROGRESS", "REJECTED"]
        )
        assert "SUBMITTED" not in data["transitions"]["READY"]
        assert "SUBMITTED" in data["approval_required_for"]


class TestCrossTenantDomainAccess:
    @pytest.mark.parametrize(
        ("collection", "attribute"),
        [
            ("client-websites", "client_website"),
            ("campaigns", "campaign"),
            ("publishers", "free_publisher"),
            ("opportunities", "opportunity"),
        ],
    )
    async def test_another_workspaces_resource_is_not_found(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict,
        tenant_b: TenantFixture,
        collection: str,
        attribute: str,
    ) -> None:
        # 404 rather than 403: a caller must not be able to confirm that an id
        # exists in another workspace.
        target = getattr(tenant_b, attribute).id
        response = await client.get(f"/api/v1/{collection}/{target}", headers=tenant_a_headers)
        assert response.status_code == 404

    async def test_another_workspaces_resource_cannot_be_modified(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, tenant_b: TenantFixture
    ) -> None:
        response = await client.patch(
            f"/api/v1/publishers/{tenant_b.free_publisher.id}",
            headers=tenant_a_headers,
            json={"name": "Renamed by another tenant"},
        )
        assert response.status_code == 404

    async def test_another_workspaces_resource_cannot_be_deleted(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, tenant_b: TenantFixture
    ) -> None:
        response = await client.delete(
            f"/api/v1/publishers/{tenant_b.free_publisher.id}", headers=tenant_a_headers
        )
        assert response.status_code == 404

    async def test_a_listing_never_includes_another_workspaces_rows(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, tenant_b: TenantFixture
    ) -> None:
        response = await client.get("/api/v1/publishers", headers=tenant_a_headers)
        domains = {row["normalized_domain"] for row in response.json()["data"]}
        assert tenant_b.free_publisher.normalized_domain not in domains

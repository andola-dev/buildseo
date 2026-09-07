"""Operational surfaces: the audit trail and the background job queue.

Both are read-mostly and both are tenant-scoped, but they matter for different
reasons. The audit trail is the record of who did what, and it must be
append-only and free of secrets. The job queue is how the product defers live
HTTP work (crawling, verification) out of the request path, and its rows must
never leak between workspaces even though a worker reads across them.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.enums import JobStatus
from app.workers.registry import TASK_PUBLISHER_QUALIFY, registered_tasks
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _enqueue_qualification(
    client: httpx.AsyncClient, headers: dict[str, str], publisher_id: str
) -> httpx.Response:
    return await client.post(
        f"/api/v1/publishers/{publisher_id}/qualify-async",
        json={"fetch_live": False, "relevance_keywords": ["software"]},
        headers=headers,
    )


class TestAuditTrail:
    async def test_creating_a_resource_writes_an_audit_entry(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        created = await client.post(
            "/api/v1/client-websites",
            json={
                "name": "Audited client",
                "website_url": "https://audited-client.test",
                "industry": "software",
            },
            headers=tenant_a_headers,
        )
        assert created.status_code == 201
        website_id = created.json()["data"]["id"]

        response = await client.get(
            "/api/v1/audit-logs",
            params={"resource_type": "client_website", "resource_id": website_id},
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        entries = response.json()["data"]
        assert entries
        assert all(entry["resource_id"] == website_id for entry in entries)

    async def test_an_entry_records_the_actor_and_the_request(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str], tenant_a: TenantFixture
    ) -> None:
        await client.post(
            "/api/v1/client-websites",
            json={"name": "Actor test", "website_url": "https://actor-test.test"},
            headers=tenant_a_headers,
        )
        response = await client.get(
            "/api/v1/audit-logs",
            params={"resource_type": "client_website"},
            headers=tenant_a_headers,
        )
        entry = response.json()["data"][0]
        assert entry["user_id"] == str(tenant_a.owner.id)
        assert entry["request_id"]

    async def test_metadata_is_allow_listed_not_a_request_body_dump(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """A raw-body dump would eventually carry a password or an API key."""
        await client.post(
            "/api/v1/client-websites",
            json={
                "name": "Allow-list test",
                "website_url": "https://allowlist-test.test",
                "description": "A long description that has no business being audited",
            },
            headers=tenant_a_headers,
        )
        response = await client.get(
            "/api/v1/audit-logs",
            params={"resource_type": "client_website"},
            headers=tenant_a_headers,
        )
        metadata = response.json()["data"][0]["metadata"]
        assert "description" not in metadata
        # Exactly the allow-list for this action, plus the common fields.
        assert set(metadata) <= {"name", "normalized_domain", "reason", "source", "job_id"}

    async def test_the_trail_is_read_only_over_http(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """No create, update or delete endpoint exists — by omission, not by check."""
        for method, path in (
            ("post", "/api/v1/audit-logs"),
            ("patch", "/api/v1/audit-logs"),
            ("delete", "/api/v1/audit-logs"),
        ):
            response = await getattr(client, method)(path, headers=tenant_a_headers)
            assert response.status_code == 405, f"{method.upper()} {path}"

    async def test_filtering_by_action_narrows_the_result(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        response = await client.get(
            "/api/v1/audit-logs",
            params={"action": "CLIENT_WEBSITE_CREATED"},
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        assert all(entry["action"] == "CLIENT_WEBSITE_CREATED" for entry in response.json()["data"])

    async def test_an_unknown_sort_field_is_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """Allow-listed, so a caller cannot sort by an unindexed column."""
        response = await client.get(
            "/api/v1/audit-logs", params={"sort": "audit_metadata"}, headers=tenant_a_headers
        )
        assert response.status_code == 422

    async def test_the_trail_does_not_cross_workspaces(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict[str, str],
        tenant_b_headers: dict[str, str],
        tenant_a: TenantFixture,
    ) -> None:
        created = await client.post(
            "/api/v1/client-websites",
            json={"name": "Private", "website_url": "https://private-a.test"},
            headers=tenant_a_headers,
        )
        website_id = created.json()["data"]["id"]

        response = await client.get(
            "/api/v1/audit-logs",
            params={"resource_id": website_id},
            headers=tenant_b_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

        theirs = await client.get("/api/v1/audit-logs", headers=tenant_b_headers)
        assert all(entry["user_id"] != str(tenant_a.owner.id) for entry in theirs.json()["data"])


class TestJobQueue:
    async def test_scheduling_work_returns_a_poll_target(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str], tenant_a: TenantFixture
    ) -> None:
        """Live HTTP work is deferred, so the request does not wait on a crawl."""
        response = await _enqueue_qualification(
            client, tenant_a_headers, str(tenant_a.free_publisher.id)
        )
        assert response.status_code == 202
        body = response.json()["data"]
        assert body["task_name"] == TASK_PUBLISHER_QUALIFY
        assert body["status"] == JobStatus.PENDING.value
        assert body["poll_url"] == f"/api/v1/jobs/{body['job_id']}"

        polled = await client.get(body["poll_url"], headers=tenant_a_headers)
        assert polled.status_code == 200
        assert polled.json()["data"]["id"] == body["job_id"]

    async def test_scheduling_against_an_unknown_publisher_is_a_404(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """The existence check happens before the job is created."""
        response = await _enqueue_qualification(
            client, tenant_a_headers, "00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404

    async def test_scheduling_against_another_workspaces_publisher_is_a_404(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict[str, str],
        tenant_b: TenantFixture,
    ) -> None:
        response = await _enqueue_qualification(
            client, tenant_a_headers, str(tenant_b.free_publisher.id)
        )
        assert response.status_code == 404

    async def test_a_job_payload_carries_no_secret(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str], tenant_a: TenantFixture
    ) -> None:
        """Handlers resolve credentials themselves; payloads stay inert."""
        accepted = await _enqueue_qualification(
            client, tenant_a_headers, str(tenant_a.free_publisher.id)
        )
        job = (
            await client.get(
                f"/api/v1/jobs/{accepted.json()['data']['job_id']}", headers=tenant_a_headers
            )
        ).json()["data"]

        flattened = str(job["payload"]).lower()
        for marker in ("secret", "api_key", "apikey", "token", "password", "authorization"):
            assert marker not in flattened

    async def test_listing_is_filterable_by_status_and_task(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str], tenant_a: TenantFixture
    ) -> None:
        await _enqueue_qualification(client, tenant_a_headers, str(tenant_a.free_publisher.id))

        response = await client.get(
            "/api/v1/jobs",
            params={"status": JobStatus.PENDING.value, "task_name": TASK_PUBLISHER_QUALIFY},
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        assert rows
        assert all(row["task_name"] == TASK_PUBLISHER_QUALIFY for row in rows)
        assert all(row["status"] == JobStatus.PENDING.value for row in rows)

    async def test_a_job_is_invisible_to_another_workspace(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict[str, str],
        tenant_b_headers: dict[str, str],
        tenant_a: TenantFixture,
    ) -> None:
        """A worker reads the queue across tenants; this endpoint does not."""
        accepted = await _enqueue_qualification(
            client, tenant_a_headers, str(tenant_a.free_publisher.id)
        )
        job_id = accepted.json()["data"]["job_id"]

        response = await client.get(f"/api/v1/jobs/{job_id}", headers=tenant_b_headers)
        assert response.status_code == 404

        listing = await client.get("/api/v1/jobs", headers=tenant_b_headers)
        assert job_id not in {row["id"] for row in listing.json()["data"]}

    async def test_the_task_type_listing_matches_the_worker_registry(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """So an operator can see what this deployment's workers can actually run."""
        response = await client.get("/api/v1/jobs/task-types", headers=tenant_a_headers)
        assert response.status_code == 200
        assert set(response.json()["data"]) == set(registered_tasks())

    async def test_there_is_no_endpoint_to_run_a_job_inline(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str], tenant_a: TenantFixture
    ) -> None:
        """Execution belongs to the worker, which re-establishes tenant context."""
        accepted = await _enqueue_qualification(
            client, tenant_a_headers, str(tenant_a.free_publisher.id)
        )
        job_id = accepted.json()["data"]["job_id"]
        for path in (f"/api/v1/jobs/{job_id}/run", f"/api/v1/jobs/{job_id}/execute"):
            response = await client.post(path, headers=tenant_a_headers)
            assert response.status_code == 404, path

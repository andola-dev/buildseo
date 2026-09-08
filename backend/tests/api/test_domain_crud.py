"""CRUD, filtering, pagination and the response envelope."""

from __future__ import annotations

import httpx
import pytest

from tests.fixtures.tenants import TenantFixture

pytestmark = pytest.mark.api


class TestResponseEnvelope:
    async def test_a_single_resource_is_wrapped_in_data(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.get(
            f"/api/v1/campaigns/{tenant_a.campaign.id}", headers=tenant_a_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"data", "meta"}
        assert body["data"]["id"] == str(tenant_a.campaign.id)

    async def test_a_collection_carries_pagination_meta(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/publishers", headers=tenant_a_headers)
        meta = response.json()["meta"]
        assert set(meta) == {
            "page",
            "page_size",
            "total",
            "total_pages",
            "has_next",
            "has_previous",
        }
        assert meta["total"] == 2
        assert meta["has_previous"] is False

    async def test_every_response_carries_a_request_id(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/publishers", headers=tenant_a_headers)
        assert response.headers["X-Request-ID"]

    async def test_secure_headers_are_present(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/publishers", headers=tenant_a_headers)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in response.headers


class TestErrorEnvelope:
    async def test_a_not_found_error_has_a_stable_code(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get(
            "/api/v1/publishers/00000000-0000-7000-8000-000000000000",
            headers=tenant_a_headers,
        )
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "PUBLISHER_NOT_FOUND"
        assert error["message"]
        assert error["details"]["request_id"]

    async def test_a_validation_error_lists_the_offending_fields(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/publishers", headers=tenant_a_headers, json={"website_url": "not a url"}
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert "website_url" in error["details"]["fields"]

    async def test_an_unknown_field_is_rejected_rather_than_ignored(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        # A typo'd or stale field name must not silently do nothing.
        response = await client.post(
            "/api/v1/publishers",
            headers=tenant_a_headers,
            json={"website_url": "https://x.test", "pricing_typ": "FREE"},
        )
        assert response.status_code == 422

    async def test_an_unknown_route_returns_the_error_envelope(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ENDPOINT_NOT_FOUND"

    async def test_no_internal_detail_leaks_into_an_error(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/publishers/not-a-uuid", headers=tenant_a_headers)
        body = response.text.lower()
        for leak in ("traceback", "sqlalchemy", "select ", "asyncpg", "/home/"):
            assert leak not in body


class TestClientWebsites:
    async def test_create_read_update_delete(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await client.post(
            "/api/v1/client-websites",
            headers=tenant_a_headers,
            json={
                "name": "Second client",
                "website_url": "https://WWW.Second-Client.test/",
                "industry": "retail",
                "target_country": "gb",
            },
        )
        assert created.status_code == 201, created.text
        data = created.json()["data"]
        # The canonical domain is derived server-side, and the country is
        # upper-cased by the schema.
        assert data["normalized_domain"] == "second-client.test"
        assert data["target_country"] == "GB"

        website_id = data["id"]
        fetched = await client.get(
            f"/api/v1/client-websites/{website_id}", headers=tenant_a_headers
        )
        assert fetched.status_code == 200

        updated = await client.patch(
            f"/api/v1/client-websites/{website_id}",
            headers=tenant_a_headers,
            json={"industry": "fashion"},
        )
        assert updated.json()["data"]["industry"] == "fashion"

        deleted = await client.delete(
            f"/api/v1/client-websites/{website_id}", headers=tenant_a_headers
        )
        assert deleted.status_code == 204
        assert (
            await client.get(f"/api/v1/client-websites/{website_id}", headers=tenant_a_headers)
        ).status_code == 404

    async def test_a_duplicate_domain_is_a_conflict_naming_the_existing_row(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/client-websites",
            headers=tenant_a_headers,
            json={
                "name": "Duplicate",
                # A different spelling of the existing client's domain.
                "website_url": "https://www.tenant-a-client.test",
            },
        )
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "CLIENT_WEBSITE_EXISTS"
        assert error["details"]["existing_id"] == str(tenant_a.client_website.id)


class TestPublishers:
    async def test_domain_normalisation_prevents_a_duplicate(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        first = await client.post(
            "/api/v1/publishers",
            headers=tenant_a_headers,
            json={"website_url": "https://example-dir.test/"},
        )
        assert first.status_code == 201
        assert first.json()["data"]["normalized_domain"] == "example-dir.test"

        for spelling in (
            "https://www.example-dir.test",
            "http://example-dir.test/listings",
            "example-dir.test",
        ):
            duplicate = await client.post(
                "/api/v1/publishers",
                headers=tenant_a_headers,
                json={"website_url": spelling},
            )
            assert duplicate.status_code == 409, spelling

    async def test_free_and_qualified_publishers_are_marked_submittable(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get(
            "/api/v1/publishers?free_only=true&status=QUALIFIED", headers=tenant_a_headers
        )
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["pricing_type"] == "FREE"
        assert rows[0]["is_submittable"] is True

    async def test_a_paid_publisher_is_stored_but_not_submittable(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.get(
            f"/api/v1/publishers/{tenant_a.paid_publisher.id}", headers=tenant_a_headers
        )
        data = response.json()["data"]
        assert data["pricing_type"] == "PAID"
        assert data["is_submittable"] is False

    async def test_filtering_and_search(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        by_pricing = await client.get(
            "/api/v1/publishers?pricing_type=PAID", headers=tenant_a_headers
        )
        assert len(by_pricing.json()["data"]) == 1

        by_search = await client.get("/api/v1/publishers?q=freedir", headers=tenant_a_headers)
        assert len(by_search.json()["data"]) == 1

        by_country = await client.get("/api/v1/publishers?country=US", headers=tenant_a_headers)
        assert len(by_country.json()["data"]) == 1


class TestPaginationAndSorting:
    async def test_paging_walks_the_whole_collection_without_gaps(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        for index in range(7):
            created = await client.post(
                "/api/v1/publishers",
                headers=tenant_a_headers,
                json={"website_url": f"https://page-{index}.test"},
            )
            assert created.status_code == 201

        seen: list[str] = []
        page = 1
        while True:
            response = await client.get(
                f"/api/v1/publishers?page={page}&page_size=3&sort=created_at&order=asc",
                headers=tenant_a_headers,
            )
            body = response.json()
            seen.extend(row["id"] for row in body["data"])
            if not body["meta"]["has_next"]:
                break
            page += 1

        # 7 created plus the 2 fixture publishers, each seen exactly once.
        assert len(seen) == 9
        assert len(set(seen)) == 9

    async def test_page_size_is_clamped_to_the_configured_maximum(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, settings
    ) -> None:
        response = await client.get("/api/v1/publishers?page_size=100000", headers=tenant_a_headers)
        assert response.json()["meta"]["page_size"] == settings.max_page_size

    async def test_sorting_in_both_directions(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        ascending = await client.get(
            "/api/v1/publishers?sort=normalized_domain&order=asc", headers=tenant_a_headers
        )
        descending = await client.get(
            "/api/v1/publishers?sort=normalized_domain&order=desc", headers=tenant_a_headers
        )
        forward = [row["normalized_domain"] for row in ascending.json()["data"]]
        backward = [row["normalized_domain"] for row in descending.json()["data"]]
        assert forward == sorted(forward)
        assert backward == list(reversed(forward))

    async def test_an_unsortable_field_is_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        # Rejecting rather than ignoring: a caller must never believe it sorted
        # when it did not, and ORDER BY must never take arbitrary input.
        response = await client.get("/api/v1/publishers?sort=tenant_id", headers=tenant_a_headers)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "INVALID_SORT_FIELD"
        assert "sortable" in error["message"].lower()
        # The caller is told what they may sort by, rather than just refused.
        assert "created_at" in error["details"]["allowed"]
        # And never the column they asked for, which is not sortable for a reason.
        assert "tenant_id" not in error["details"]["allowed"]

    async def test_an_out_of_range_page_returns_an_empty_page_not_an_error(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        response = await client.get("/api/v1/publishers?page=999", headers=tenant_a_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestCampaigns:
    async def test_free_only_is_not_accepted_as_an_input(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        # The platform builds free listings; the column is pinned by the
        # database, so accepting the field would only allow a guaranteed
        # rejection.
        response = await client.post(
            "/api/v1/campaigns",
            headers=tenant_a_headers,
            json={
                "client_website_id": str(tenant_a.client_website.id),
                "name": "Paid attempt",
                "free_only": False,
            },
        )
        assert response.status_code == 422

    async def test_a_created_campaign_is_always_free_only(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/campaigns",
            headers=tenant_a_headers,
            json={
                "client_website_id": str(tenant_a.client_website.id),
                "name": "Second campaign",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["free_only"] is True

    async def test_country_and_language_are_inherited_from_the_client_site(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/campaigns",
            headers=tenant_a_headers,
            json={
                "client_website_id": str(tenant_a.client_website.id),
                "name": "Inheriting campaign",
            },
        )
        data = response.json()["data"]
        assert data["target_country"] == "US"
        assert data["target_language"] == "en"

    async def test_a_campaign_for_another_workspaces_client_site_is_not_found(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict,
        tenant_b: TenantFixture,
    ) -> None:
        response = await client.post(
            "/api/v1/campaigns",
            headers=tenant_a_headers,
            json={
                "client_website_id": str(tenant_b.client_website.id),
                "name": "Cross-tenant",
            },
        )
        assert response.status_code == 404

    async def test_campaign_stats(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.get(
            f"/api/v1/campaigns/{tenant_a.campaign.id}/stats", headers=tenant_a_headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["opportunities_total"] == 1
        assert data["submissions_total"] == 0
        assert data["target_link_count"] == 25

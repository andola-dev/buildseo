"""Credential secrets must never leave the service layer.

The BYOK promise is that a tenant's provider key is unreadable after it is
stored. These tests attack that from every direction the API offers.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import TenantAwareSession
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.security, pytest.mark.api]

SECRET = "sk-live-supersecret-0123456789abcdef"


async def _store_credential(
    client: httpx.AsyncClient, headers: dict[str, str], *, label: str = "Prod"
) -> dict:
    response = await client.post(
        "/api/v1/credentials",
        headers=headers,
        json={
            "provider": "openai",
            "provider_type": "AI",
            "label": label,
            "secret": SECRET,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestResponsesNeverCarryTheSecret:
    async def test_the_create_response_returns_only_a_masked_hint(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers)
        assert SECRET not in json.dumps(created)
        assert created["masked_key"] == "sk-****cdef"
        for forbidden in ("secret", "ciphertext", "encrypted_dek", "nonce", "dek_nonce"):
            assert forbidden not in created

    async def test_the_get_response_returns_only_a_masked_hint(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="Get")
        response = await client.get(
            f"/api/v1/credentials/{created['id']}", headers=tenant_a_headers
        )
        assert response.status_code == 200
        assert SECRET not in response.text

    async def test_the_list_response_returns_only_masked_hints(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        await _store_credential(client, tenant_a_headers, label="List")
        response = await client.get("/api/v1/credentials", headers=tenant_a_headers)
        assert SECRET not in response.text

    async def test_there_is_no_endpoint_that_reveals_a_secret(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="Reveal")
        for path in ("secret", "reveal", "decrypt", "plaintext", "value"):
            response = await client.get(
                f"/api/v1/credentials/{created['id']}/{path}", headers=tenant_a_headers
            )
            assert response.status_code in (404, 405), path


class TestStorage:
    async def test_the_secret_is_not_stored_in_plaintext(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict,
        session_factory: async_sessionmaker[TenantAwareSession],
    ) -> None:
        await _store_credential(client, tenant_a_headers, label="Storage")
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT ciphertext, encrypted_dek, masked_hint, metadata::text "
                        "FROM credentials"
                    )
                )
            ).all()
        assert rows
        raw = SECRET.encode()
        for ciphertext, encrypted_dek, masked_hint, metadata in rows:
            assert raw not in bytes(ciphertext)
            assert raw not in bytes(encrypted_dek)
            assert SECRET not in masked_hint
            assert SECRET not in metadata


class TestMetadataCannotSmuggleASecret:
    @pytest.mark.parametrize(
        "field", ["api_key", "secret", "password", "access_token", "client_secret"]
    )
    async def test_secret_shaped_metadata_keys_are_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, field: str
    ) -> None:
        # metadata is stored unencrypted and returned by the API, so allowing a
        # key there would defeat the encryption entirely.
        response = await client.post(
            "/api/v1/credentials",
            headers=tenant_a_headers,
            json={
                "provider": "openai",
                "label": f"Metadata {field}",
                "secret": SECRET,
                "metadata": {field: "smuggled"},
            },
        )
        assert response.status_code == 422

    async def test_secret_shaped_ai_parameters_are_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="Params")
        response = await client.put(
            "/api/v1/ai/configs",
            headers=tenant_a_headers,
            json={
                "purpose": "content_generation",
                "provider": "openai",
                "model": "gpt-4o",
                "credential_id": created["id"],
                "parameters": {"api_key": "smuggled"},
            },
        )
        assert response.status_code == 422

    async def test_workspace_settings_cannot_hold_a_secret(
        self, client: httpx.AsyncClient, tenant_a: TenantFixture, tenant_a_headers: dict
    ) -> None:
        response = await client.patch(
            f"/api/v1/tenants/{tenant_a.tenant_id}",
            headers=tenant_a_headers,
            json={"settings": {"openai_api_key": SECRET}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SECRET_IN_SETTINGS"


class TestCrossTenantCredentialAccess:
    async def test_a_credential_is_invisible_to_another_workspace(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict,
        tenant_b_headers: dict,
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="Cross")

        # 404, not 403: a caller must not be able to confirm that an id exists
        # in someone else's workspace.
        response = await client.get(
            f"/api/v1/credentials/{created['id']}", headers=tenant_b_headers
        )
        assert response.status_code == 404

        listing = await client.get("/api/v1/credentials", headers=tenant_b_headers)
        assert listing.json()["data"] == []

    async def test_another_workspace_cannot_delete_it(
        self, client: httpx.AsyncClient, tenant_a_headers: dict, tenant_b_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="CrossDelete")
        response = await client.delete(
            f"/api/v1/credentials/{created['id']}", headers=tenant_b_headers
        )
        assert response.status_code == 404

        still_there = await client.get(
            f"/api/v1/credentials/{created['id']}", headers=tenant_a_headers
        )
        assert still_there.status_code == 200


class TestAuditTrail:
    async def test_the_audit_record_names_the_provider_never_the_key(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        await _store_credential(client, tenant_a_headers, label="Audited")
        response = await client.get(
            "/api/v1/audit-logs?action=CREDENTIAL_CREATED", headers=tenant_a_headers
        )
        assert response.status_code == 200
        body = response.text
        assert SECRET not in body
        entry = response.json()["data"][0]
        assert entry["metadata"]["provider"] == "openai"
        assert "masked_hint" not in entry["metadata"]


class TestRotation:
    async def test_rotating_replaces_the_hint_and_resets_verification(
        self, client: httpx.AsyncClient, tenant_a_headers: dict
    ) -> None:
        created = await _store_credential(client, tenant_a_headers, label="Rotate")
        rotated = await client.patch(
            f"/api/v1/credentials/{created['id']}",
            headers=tenant_a_headers,
            json={"secret": "sk-live-rotated-9876543210zyxwvu"},
        )
        assert rotated.status_code == 200
        data = rotated.json()["data"]
        assert data["masked_key"] == "sk-****xwvu"
        # A rotated key is unproven until it is used or verified again.
        assert data["status"] == "CONFIGURED"
        assert data["last_verified_at"] is None
        assert SECRET not in rotated.text

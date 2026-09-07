"""BYOK credentials and per-workspace AI configuration, over HTTP.

The point of BYOK is that the platform holds no global provider key: each
workspace supplies its own, and business code asks for a *purpose*
(``content_generation``) rather than a vendor. These tests exercise that from
the outside — storing a key, pointing a purpose at it, moving the default, and
the refusals that keep the arrangement coherent.

Secret non-disclosure is asserted in ``tests/security/test_credential_leakage``;
this module is about the workflow.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.enums import AiProvider, AiPurpose, CredentialStatus
from app.schemas.ai import AiUsageRead

pytestmark = [pytest.mark.api, pytest.mark.asyncio]

# Obviously fake, and never sent anywhere: FormSubmissionProvider and the AI
# clients are not invoked because `verify` is left off in these tests.
FAKE_SECRET = "test-not-a-real-key-000000000000"


async def _create_credential(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    provider: str = AiProvider.ANTHROPIC.value,
    label: str = "primary",
    metadata: dict[str, object] | None = None,
    idempotency_key: str | None = None,
) -> httpx.Response:
    request_headers = dict(headers)
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    return await client.post(
        "/api/v1/credentials",
        json={
            "provider": provider,
            "label": label,
            "secret": FAKE_SECRET,
            "metadata": metadata or {},
        },
        headers=request_headers,
    )


class TestCredentialLifecycle:
    async def test_a_stored_credential_starts_unverified(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """A key nobody has used yet is CONFIGURED, not VERIFIED."""
        response = await _create_credential(client, tenant_a_headers)
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["status"] == CredentialStatus.CONFIGURED.value
        assert body["last_verified_at"] is None
        assert body["key_version"] == 1

    async def test_the_same_provider_may_hold_several_labelled_keys(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        for label in ("primary", "fallback"):
            response = await _create_credential(client, tenant_a_headers, label=label)
            assert response.status_code == 201

        listing = await client.get("/api/v1/credentials", headers=tenant_a_headers)
        assert listing.status_code == 200
        assert {row["label"] for row in listing.json()["data"]} == {"primary", "fallback"}

    async def test_a_duplicate_label_is_a_conflict(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        assert (await _create_credential(client, tenant_a_headers)).status_code == 201
        duplicate = await _create_credential(client, tenant_a_headers)
        assert duplicate.status_code == 409

    async def test_a_replayed_create_returns_the_original(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """The fingerprint excludes the secret, so a genuine retry matches."""
        first = await _create_credential(
            client, tenant_a_headers, idempotency_key="store-anthropic-key"
        )
        assert first.status_code == 201

        replay = await _create_credential(
            client, tenant_a_headers, idempotency_key="store-anthropic-key"
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["id"] == first.json()["data"]["id"]
        assert replay.json()["meta"]["replayed"] is True

    async def test_listing_filters_by_provider_and_status(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        await _create_credential(client, tenant_a_headers, provider="anthropic", label="a")
        await _create_credential(client, tenant_a_headers, provider="openai", label="b")

        response = await client.get(
            "/api/v1/credentials",
            params={"provider": "openai", "status": CredentialStatus.CONFIGURED.value},
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        assert [row["provider"] for row in response.json()["data"]] == ["openai"]

    async def test_a_credential_can_be_retired_without_deleting_it(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """DISABLED keeps the audit trail intact while stopping all use."""
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]

        response = await client.patch(
            f"/api/v1/credentials/{credential_id}",
            json={"status": CredentialStatus.DISABLED.value},
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == CredentialStatus.DISABLED.value

    async def test_deleting_a_credential_removes_it(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]

        assert (
            await client.delete(f"/api/v1/credentials/{credential_id}", headers=tenant_a_headers)
        ).status_code == 204
        assert (
            await client.get(f"/api/v1/credentials/{credential_id}", headers=tenant_a_headers)
        ).status_code == 404

    async def test_a_blank_or_placeholder_secret_is_rejected(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """Catches a caller who pasted the OpenAPI example."""
        response = await client.post(
            "/api/v1/credentials",
            json={"provider": "anthropic", "label": "oops", "secret": "changeme"},
            headers=tenant_a_headers,
        )
        assert response.status_code == 422


class TestAiConfiguration:
    async def test_a_purpose_can_be_pointed_at_a_credential(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]

        response = await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.ANTHROPIC.value,
                "model": "claude-opus-5",
                "credential_id": credential_id,
                "is_default": True,
            },
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["purpose"] == AiPurpose.CONTENT_GENERATION.value
        assert body["credential_id"] == credential_id
        assert body["is_default"] is True

    async def test_upserting_the_same_purpose_and_provider_updates_in_place(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]
        payload = {
            "purpose": AiPurpose.CONTENT_GENERATION.value,
            "provider": AiProvider.ANTHROPIC.value,
            "model": "claude-opus-5",
            "credential_id": credential_id,
            "is_default": True,
        }
        first = await client.put("/api/v1/ai/configs", json=payload, headers=tenant_a_headers)
        second = await client.put(
            "/api/v1/ai/configs",
            json={**payload, "model": "claude-sonnet-5"},
            headers=tenant_a_headers,
        )
        assert second.status_code == 200
        assert second.json()["data"]["id"] == first.json()["data"]["id"]
        assert second.json()["data"]["model"] == "claude-sonnet-5"

    async def test_moving_the_default_leaves_exactly_one(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """Enforced by a partial unique index, so this cannot drift."""
        anthropic = (await _create_credential(client, tenant_a_headers, label="anthropic")).json()
        openai = (
            await _create_credential(client, tenant_a_headers, provider="openai", label="openai")
        ).json()

        for provider, credential in (
            (AiProvider.ANTHROPIC.value, anthropic),
            (AiProvider.OPENAI.value, openai),
        ):
            response = await client.put(
                "/api/v1/ai/configs",
                json={
                    "purpose": AiPurpose.CONTENT_GENERATION.value,
                    "provider": provider,
                    "model": "a-model",
                    "credential_id": credential["data"]["id"],
                    "is_default": True,
                },
                headers=tenant_a_headers,
            )
            assert response.status_code == 200

        listing = await client.get("/api/v1/ai/configs", headers=tenant_a_headers)
        defaults = [
            row
            for row in listing.json()["data"]
            if row["purpose"] == AiPurpose.CONTENT_GENERATION.value and row["is_default"]
        ]
        assert len(defaults) == 1
        assert defaults[0]["provider"] == AiProvider.OPENAI.value

    async def test_a_credential_is_required_for_a_hosted_provider(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """There is no global fallback key to quietly use instead."""
        response = await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.ANTHROPIC.value,
                "model": "claude-opus-5",
                "is_default": True,
            },
            headers=tenant_a_headers,
        )
        assert response.status_code == 422

    async def test_a_self_hosted_custom_endpoint_needs_no_credential(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.CUSTOM.value,
                "model": "local-model",
                "parameters": {"base_url": "https://llm.internal.test/v1"},
                "is_default": True,
            },
            headers=tenant_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["credential_id"] is None

    async def test_pointing_at_another_workspaces_credential_is_a_404(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict[str, str],
        tenant_b_headers: dict[str, str],
    ) -> None:
        """Not a 403: an identifier's existence elsewhere must not be probeable."""
        theirs = await _create_credential(client, tenant_b_headers, label="theirs")
        response = await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.ANTHROPIC.value,
                "model": "claude-opus-5",
                "credential_id": theirs.json()["data"]["id"],
                "is_default": True,
            },
            headers=tenant_a_headers,
        )
        assert response.status_code == 404

    async def test_deleting_a_referenced_credential_is_refused(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        """Silently disabling generation would be worse than an explicit error."""
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]
        await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.ANTHROPIC.value,
                "model": "claude-opus-5",
                "credential_id": credential_id,
                "is_default": True,
            },
            headers=tenant_a_headers,
        )

        response = await client.delete(
            f"/api/v1/credentials/{credential_id}", headers=tenant_a_headers
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CREDENTIAL_IN_USE"

    async def test_removing_a_configuration_leaves_other_purposes_alone(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        created = await _create_credential(client, tenant_a_headers)
        credential_id = created.json()["data"]["id"]
        ids = {}
        for purpose in (AiPurpose.CONTENT_GENERATION, AiPurpose.QUALIFICATION):
            response = await client.put(
                "/api/v1/ai/configs",
                json={
                    "purpose": purpose.value,
                    "provider": AiProvider.ANTHROPIC.value,
                    "model": "claude-opus-5",
                    "credential_id": credential_id,
                    "is_default": True,
                },
                headers=tenant_a_headers,
            )
            ids[purpose] = response.json()["data"]["id"]

        deleted = await client.delete(
            f"/api/v1/ai/configs/{ids[AiPurpose.QUALIFICATION]}", headers=tenant_a_headers
        )
        assert deleted.status_code == 200

        listing = await client.get("/api/v1/ai/configs", headers=tenant_a_headers)
        remaining = {row["purpose"] for row in listing.json()["data"]}
        assert remaining == {AiPurpose.CONTENT_GENERATION.value}

    async def test_configuration_does_not_cross_workspaces(
        self,
        client: httpx.AsyncClient,
        tenant_a_headers: dict[str, str],
        tenant_b_headers: dict[str, str],
    ) -> None:
        created = await _create_credential(client, tenant_a_headers)
        await client.put(
            "/api/v1/ai/configs",
            json={
                "purpose": AiPurpose.CONTENT_GENERATION.value,
                "provider": AiProvider.ANTHROPIC.value,
                "model": "claude-opus-5",
                "credential_id": created.json()["data"]["id"],
                "is_default": True,
            },
            headers=tenant_a_headers,
        )

        theirs = await client.get("/api/v1/ai/configs", headers=tenant_b_headers)
        assert theirs.status_code == 200
        assert theirs.json()["data"] == []


class TestAiUsageAccounting:
    async def test_a_workspace_with_no_calls_reports_zeroes(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/v1/ai/usage/summary", headers=tenant_a_headers)
        assert response.status_code == 200
        summary = response.json()["data"]
        assert summary["total_requests"] == 0
        assert summary["total_estimated_cost"] == 0
        assert summary["rows"] == []

    async def test_the_usage_ledger_is_empty_and_paginated(
        self, client: httpx.AsyncClient, tenant_a_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/v1/ai/usage", headers=tenant_a_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []
        assert response.json()["meta"]["total"] == 0

    def test_no_usage_field_can_carry_prompt_or_completion_text(self) -> None:
        """Prompts are not stored, so the schema has nowhere to put one."""
        forbidden = {"prompt", "completion", "response", "text", "messages", "content"}
        assert forbidden.isdisjoint(set(AiUsageRead.model_fields))

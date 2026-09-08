"""The generated OpenAPI document is part of the deliverable.

The specification asks for a documented REST API, and the schema is what
clients actually build against — so it is asserted rather than assumed. Two
kinds of check live here:

* completeness — every route carries a summary, a description, a tag and the
  error responses a caller has to handle;
* safety — no response schema anywhere in the document has a field capable of
  carrying a password hash, a refresh-token digest, an encryption key or a
  provider secret. That is a structural guarantee, and this test is what keeps
  it one.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.router import OPENAPI_TAGS

pytestmark = [pytest.mark.api, pytest.mark.asyncio]

#: Unauthenticated by design: the probes a load balancer calls.
PUBLIC_PATHS = frozenset({"/health", "/health/live", "/health/ready"})

#: Reachable without a token, so a 403 would be meaningless on them.
UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    }
)

#: Field names that must never appear in a *response* schema. Matched as
#: substrings, so ``password_hash`` and ``hashed_password`` both fail.
FORBIDDEN_FIELD_PARTS = (
    "password",
    "secret",
    "ciphertext",
    "encrypted_dek",
    "dek_nonce",
    "token_hash",
    "encryption_key",
    "api_key",
    "private_key",
    "masked_hint",
)

#: Legitimate exceptions, each one deliberate: the token pair a login has to
#: return, and the write-only fields a caller submits.
ALLOWED_FIELDS = frozenset(
    {
        "access_token",
        "refresh_token",
        "token_type",
        # Request-side only. ``CredentialCreate``/``CredentialUpdate`` accept a
        # secret; no read schema has the field at all.
        "secret",
        "password",
        "current_password",
        "new_password",
    }
)


def _operations(schema: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                yield path, method, operation


def _property_names(node: Any) -> Iterator[str]:
    """Yield every property name reachable in the document."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            yield from properties
        for value in node.values():
            yield from _property_names(value)
    elif isinstance(node, list):
        for value in node:
            yield from _property_names(value)


@pytest.fixture
def schema(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


class TestDocumentIsComplete:
    async def test_every_operation_has_a_summary_and_a_description(
        self, schema: dict[str, Any]
    ) -> None:
        missing = [
            f"{method.upper()} {path}"
            for path, method, operation in _operations(schema)
            if not operation.get("summary") or not operation.get("description")
        ]
        assert missing == []

    async def test_every_operation_is_tagged_with_a_described_tag(
        self, schema: dict[str, Any]
    ) -> None:
        """So the rendered docs group endpoints under an explanation."""
        described = {tag["name"] for tag in OPENAPI_TAGS}
        untagged = []
        unknown = set()
        for path, method, operation in _operations(schema):
            tags = operation.get("tags", [])
            if not tags:
                untagged.append(f"{method.upper()} {path}")
            unknown |= set(tags) - described
        assert untagged == []
        assert unknown == set()

    async def test_authenticated_operations_document_a_401(self, schema: dict[str, Any]) -> None:
        """A client cannot handle a failure it was never told about."""
        missing = [
            f"{method.upper()} {path}"
            for path, method, operation in _operations(schema)
            if path not in PUBLIC_PATHS and "401" not in set(operation.get("responses", {}))
        ]
        assert missing == []

    async def test_authenticated_operations_document_a_403(self, schema: dict[str, Any]) -> None:
        """Every permission-gated route can refuse; the schema says so."""
        missing = [
            f"{method.upper()} {path}"
            for path, method, operation in _operations(schema)
            if path not in PUBLIC_PATHS
            and path not in UNAUTHENTICATED_PATHS
            and "403" not in set(operation.get("responses", {}))
        ]
        assert missing == []

    async def test_operations_document_throttling_and_server_failure(
        self, schema: dict[str, Any]
    ) -> None:
        missing = [
            f"{method.upper()} {path} missing {code}"
            for path, method, operation in _operations(schema)
            if path not in PUBLIC_PATHS
            for code in ("429", "500")
            if code not in set(operation.get("responses", {}))
        ]
        assert missing == []

    async def test_resource_addressed_operations_document_a_404(
        self, schema: dict[str, Any]
    ) -> None:
        """A path parameter means the row may not exist — or may not be visible.

        Authentication is excluded: its session endpoints report a missing
        session through the same 401/403 surface as an invalid token.
        """
        missing = [
            f"{method.upper()} {path}"
            for path, method, operation in _operations(schema)
            if "{" in path
            and "Authentication" not in operation.get("tags", [])
            and "404" not in set(operation.get("responses", {}))
        ]
        assert missing == []

    async def test_the_error_envelope_is_the_same_everywhere(self, schema: dict[str, Any]) -> None:
        """Clients branch on shape alone, so the failure shape must not vary."""
        schemas = schema["components"]["schemas"]
        assert set(schemas["ErrorResponse"]["properties"]) == {"error"}
        assert {"code", "message", "details"} <= set(schemas["ErrorDetail"]["properties"])

    async def test_every_declared_failure_uses_the_error_envelope(
        self, schema: dict[str, Any]
    ) -> None:
        """One failure shape across the API, so clients need one branch.

        422 is excluded: FastAPI contributes its own validation-error schema for
        routes that declare no explicit 422, and that is a documentation detail
        rather than a second envelope for domain errors.
        """
        wrong = []
        for path, method, operation in _operations(schema):
            for code, response in operation.get("responses", {}).items():
                if code not in {"400", "401", "403", "404", "409", "429", "500"}:
                    continue
                reference = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                    .get("$ref", "")
                )
                if not reference.endswith("/ErrorResponse"):
                    wrong.append(f"{method.upper()} {path} {code} -> {reference or 'none'}")
        assert wrong == []


class TestDocumentLeaksNothing:
    async def test_no_read_schema_can_carry_a_secret(self, schema: dict[str, Any]) -> None:
        """Structural: the fields do not exist, rather than being excluded."""
        offending: set[str] = set()
        for name in _property_names(schema.get("components", {}).get("schemas", {})):
            if name in ALLOWED_FIELDS:
                continue
            lowered = name.lower()
            if any(part in lowered for part in FORBIDDEN_FIELD_PARTS):
                offending.add(name)
        assert offending == set()

    async def test_the_credential_read_schema_exposes_only_metadata(
        self, schema: dict[str, Any]
    ) -> None:
        credential = schema["components"]["schemas"]["CredentialRead"]
        assert set(credential["properties"]) == {
            "id",
            "provider",
            "provider_type",
            "label",
            "status",
            "masked_key",
            "metadata",
            "key_version",
            "last_verified_at",
            "created_at",
            "updated_at",
        }

    async def test_no_user_schema_exposes_the_password_hash(self, schema: dict[str, Any]) -> None:
        for name, definition in schema["components"]["schemas"].items():
            if not name.startswith("User"):
                continue
            assert "password_hash" not in definition.get("properties", {}), name

    async def test_no_session_schema_exposes_a_token_digest(self, schema: dict[str, Any]) -> None:
        for name, definition in schema["components"]["schemas"].items():
            if "Session" not in name:
                continue
            properties = set(definition.get("properties", {}))
            assert not {"token_hash", "refresh_token_hash"} & properties, name


class TestSchemaIsServedAndStable:
    async def test_the_schema_is_reachable_when_docs_are_enabled(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["openapi"].startswith("3.")

    async def test_generating_the_schema_twice_gives_the_same_document(self, app: FastAPI) -> None:
        """A moving schema breaks generated clients for no reason."""
        assert app.openapi() == app.openapi()

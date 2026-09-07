"""Idempotency-key handling for unsafe operations.

A client that times out mid-POST cannot tell whether the write happened.
Replaying the same ``Idempotency-Key`` returns the stored response instead of
creating a second publisher, opportunity, submission or credential.

Reusing a key with a *different* body is a client bug and is rejected with 409
rather than silently returning an unrelated earlier response.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request

from app.api.dependencies.services import ServicesDep
from app.config.logging import get_logger
from app.core.exceptions import IdempotencyConflictError
from app.models.idempotency import IdempotencyKey
from app.repositories.idempotency import IdempotencyKeyRepository

logger = get_logger(__name__)

IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=128,
        description=(
            "Optional. Replaying a request with the same key returns the original "
            "response instead of creating a duplicate resource."
        ),
    ),
]


def request_fingerprint(payload: Any) -> str:
    """Stable digest of a request body.

    ``sort_keys`` matters: two logically identical bodies with different key
    order must produce the same fingerprint, or a legitimate retry would look
    like a conflicting reuse.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IdempotencyGuard:
    """Reads and writes the idempotency ledger for one request."""

    repository: IdempotencyKeyRepository
    key: str | None
    endpoint: str

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    async def existing(self, payload: Any) -> IdempotencyKey | None:
        """Return the prior record for this key, if the body matches."""
        if not self.key:
            return None
        record = await self.repository.get(self.key, self.endpoint)
        if record is None:
            return None
        if record.request_hash != request_fingerprint(payload):
            logger.warning(
                "idempotency key reused with a different body",
                extra={"endpoint": self.endpoint},
            )
            raise IdempotencyConflictError(
                details={"endpoint": self.endpoint},
            )
        return record

    async def remember(
        self, payload: Any, *, status_code: int, body: dict[str, Any], resource_id: str | None
    ) -> None:
        """Store the outcome so a replay can return it."""
        if not self.key:
            return
        self.repository.new(
            key=self.key,
            endpoint=self.endpoint,
            request_hash=request_fingerprint(payload),
            response_status=status_code,
            response_body=body,
            resource_id=resource_id,
        )
        await self.repository.flush()


async def get_idempotency_guard(
    request: Request,
    services: ServicesDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> IdempotencyGuard:
    """Build the guard for this request.

    The endpoint is keyed as ``METHOD route-template``, so the same key may be
    reused across distinct endpoints without colliding, and two different
    bodies sent to the same endpoint with one key still conflict.
    """
    route = request.scope.get("route")
    endpoint = f"{request.method} {getattr(route, 'path', request.url.path)}"
    return IdempotencyGuard(
        repository=services.idempotency_keys, key=idempotency_key, endpoint=endpoint
    )


IdempotencyGuardDep = Annotated[IdempotencyGuard, Depends(get_idempotency_guard)]

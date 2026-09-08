"""Audit log schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import IPAddressStr, ReadSchemaBase


class AuditLogRead(ReadSchemaBase):
    """One audited action.

    ``metadata`` is assembled from per-action allow-lists in the audit service,
    never from a raw request body, so it cannot contain a password or an API
    key.
    """

    id: UUID
    user_id: UUID | None = None
    action: str = Field(description="Stable action code, e.g. PUBLISHER_CREATED")
    resource_type: str | None = None
    resource_id: str | None = None
    audit_metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="audit_metadata",
        serialization_alias="metadata",
        description="Allow-listed, non-sensitive context",
    )
    ip_address: IPAddressStr | None = None
    user_agent: str | None = None
    request_id: str | None = None
    created_at: datetime

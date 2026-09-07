"""Idempotency keys for unsafe operations."""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, TenantOwnedMixin, UUIDPrimaryKeyMixin


class IdempotencyKey(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, CreatedAtMixin):
    """Records the outcome of a keyed request so a retry replays it.

    A client that times out mid-POST cannot tell whether the write happened.
    Sending the same ``Idempotency-Key`` again returns the stored response
    instead of creating a second publisher, opportunity, submission or
    credential.

    ``request_hash`` is a digest of the canonicalised request body. Reusing a
    key with a *different* body is a client bug, and is rejected with 409
    rather than silently returning the earlier, unrelated response.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "key", "endpoint", name="uq_idempotency_keys_tenant_key_endpoint"
        ),
        Index("ix_idempotency_keys_created_at", "created_at"),
        {"comment": "Tenant-owned idempotency ledger for unsafe operations."},
    )

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: ``METHOD path`` so the same key may be reused across distinct endpoints.
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    #: Id of the resource the original call created, for convenience.
    resource_id: Mapped[str | None] = mapped_column(String(64))

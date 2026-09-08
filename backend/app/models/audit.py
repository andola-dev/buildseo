"""Audit log."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, TenantOwnedMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, CreatedAtMixin):
    """A security- or business-significant action.

    Append-only by design: there is no update path and no delete endpoint, so
    the trail cannot be quietly rewritten. ``metadata`` is assembled from
    per-action allow-lists in the audit service rather than from raw request
    bodies, which is what keeps secrets out of it — a request body could carry
    a password or an API key, an allow-listed field set cannot.

    ``user_id`` is nullable (``SET NULL`` on user deletion) so the record of an
    action outlives the account that performed it. ``resource_id`` is text
    rather than a UUID because some audited resources are identified by a
    natural key.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_id_action", "tenant_id", "action"),
        Index("ix_audit_logs_tenant_id_user_id", "tenant_id", "user_id"),
        Index(
            "ix_audit_logs_tenant_id_resource",
            "tenant_id",
            "resource_type",
            "resource_id",
        ),
        {"comment": "Tenant-owned append-only audit trail. RLS protected."},
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Stable action code, e.g. ``PUBLISHER_CREATED``. See app.audit.actions.
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    #: Allow-listed, non-sensitive context only.
    audit_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(128))

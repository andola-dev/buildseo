"""Link opportunities — a campaign's chance at a listing on one publisher."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OpportunityStatus, OpportunityType


class Opportunity(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """The join of "this campaign wants a link" and "this publisher may take one"."""

    __tablename__ = "opportunities"
    __table_args__ = (
        # Idempotency: re-running discovery, or retrying a create after a
        # network timeout, must not produce a second opportunity for the same
        # campaign/publisher/target-URL triple.
        UniqueConstraint(
            "tenant_id",
            "campaign_id",
            "publisher_id",
            "target_url",
            name="uq_opportunities_tenant_campaign_publisher_target",
        ),
        CheckConstraint(OpportunityStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint(
            OpportunityType.check_constraint("opportunity_type"), name="opportunity_type_valid"
        ),
        CheckConstraint(
            "qualification_score IS NULL OR qualification_score BETWEEN 0 AND 100",
            name="qualification_score_range",
        ),
        CheckConstraint("priority BETWEEN 0 AND 100", name="priority_range"),
        Index("ix_opportunities_tenant_id_status", "tenant_id", "status"),
        Index("ix_opportunities_tenant_id_campaign_id", "tenant_id", "campaign_id"),
        Index("ix_opportunities_tenant_id_publisher_id", "tenant_id", "publisher_id"),
        Index("ix_opportunities_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_opportunities_tenant_id_updated_at", "tenant_id", "updated_at"),
        # Work queue: what a specialist should pick up next, highest priority
        # first. Partial, so the index stays small as PUBLISHED rows accumulate.
        Index(
            "ix_opportunities_tenant_id_workqueue",
            "tenant_id",
            "campaign_id",
            "priority",
            postgresql_where=text("status IN ('QUALIFIED', 'SELECTED', 'READY')"),
        ),
        {"comment": "Tenant-owned listing opportunities. RLS protected."},
    )

    campaign_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    publisher_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    #: The client URL to be listed.
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    suggested_anchor: Mapped[str | None] = mapped_column(String(255))
    suggested_title: Mapped[str | None] = mapped_column(String(255))
    suggested_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{OpportunityStatus.DISCOVERED.value}'")
    )
    qualification_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    #: 0-100 work-queue ordering; derived from the qualification score but
    #: overridable by a human.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    #: Snapshot of the publisher's submission URL at qualification time, so a
    #: later publisher edit does not silently change a queued opportunity.
    submission_url: Mapped[str | None] = mapped_column(String(2048))
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_ready_for_submission(self) -> bool:
        return self.status == OpportunityStatus.READY.value

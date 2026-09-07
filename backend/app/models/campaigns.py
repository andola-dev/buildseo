"""Campaigns — a link-building goal for one client website."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

from app.core.enums import CampaignStatus
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Campaign(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """A campaign targeting free listings for one client website."""

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "client_website_id", "name", name="uq_campaigns_tenant_website_name"
        ),
        CheckConstraint(CampaignStatus.check_constraint("status"), name="status_valid"),
        # MVP business rule 1/2: this platform builds free listings only. Paid
        # placements are out of scope, so the flag is pinned at the database
        # level rather than merely defaulted. Supporting paid publishers later
        # means dropping this one constraint in a migration — a deliberate,
        # reviewable decision instead of an accident.
        CheckConstraint("free_only", name="mvp_free_only"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="date_range_ordered",
        ),
        CheckConstraint("budget IS NULL OR budget >= 0", name="budget_non_negative"),
        CheckConstraint(
            "target_link_count IS NULL OR target_link_count > 0", name="target_link_count_positive"
        ),
        Index("ix_campaigns_tenant_id_status", "tenant_id", "status"),
        Index("ix_campaigns_tenant_id_client_website_id", "tenant_id", "client_website_id"),
        Index("ix_campaigns_tenant_id_created_at", "tenant_id", "created_at"),
        {"comment": "Tenant-owned campaigns. free_only is pinned true for the MVP."},
    )

    client_website_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("client_websites.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{CampaignStatus.DRAFT.value}'")
    )
    target_country: Mapped[str | None] = mapped_column(String(2))
    target_language: Mapped[str | None] = mapped_column(String(8))
    #: Present for planning and reporting only. Nothing in this platform spends
    #: it: there are no paid placements to buy.
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    free_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    target_link_count: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    @property
    def is_active(self) -> bool:
        return self.status == CampaignStatus.ACTIVE.value

"""Client websites — the sites a tenant is building links for."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ClientWebsiteStatus
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ClientWebsite(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """One client site or project belonging to a tenant.

    An agency tenant typically has many. Campaigns hang off a client website,
    which is what keeps one client's link goals from mixing with another's.
    """

    __tablename__ = "client_websites"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "normalized_domain", name="uq_client_websites_tenant_id_normalized_domain"
        ),
        CheckConstraint(ClientWebsiteStatus.check_constraint("status"), name="status_valid"),
        Index("ix_client_websites_tenant_id_status", "tenant_id", "status"),
        Index("ix_client_websites_tenant_id_created_at", "tenant_id", "created_at"),
        {"comment": "Tenant-owned client sites. RLS protected."},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: As supplied by the user, for display.
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    #: Canonical form from ``normalize_domain``; the de-duplication identity.
    normalized_domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(120), index=True)
    #: Primary market, ISO 3166-1 alpha-2.
    target_country: Mapped[str | None] = mapped_column(String(2))
    #: Additional markets. JSONB because it is a genuinely variable-length list
    #: with no relational query need beyond containment.
    target_countries: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: ISO 639-1.
    target_language: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{ClientWebsiteStatus.ACTIVE.value}'")
    )

"""Publishers — websites that may accept a free listing — and discovery runs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    DiscoveryRunStatus,
    LinkType,
    PricingType,
    PublisherCategory,
    PublisherStatus,
    SubmissionMethod,
)
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Publisher(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """A candidate listing site.

    Publishers are tenant-owned rather than shared platform-wide. That is a
    deliberate isolation choice: a tenant's research, scores, notes and
    rejection decisions are competitive information, and a shared table would
    make one tenant's edits visible to another. De-duplication is therefore
    per tenant, keyed on ``normalized_domain``.
    """

    __tablename__ = "publishers"
    __table_args__ = (
        # The canonical identity: example.com, www.example.com and
        # https://example.com/ all reduce to one row per tenant.
        UniqueConstraint(
            "tenant_id", "normalized_domain", name="uq_publishers_tenant_id_normalized_domain"
        ),
        CheckConstraint(PricingType.check_constraint("pricing_type"), name="pricing_type_valid"),
        CheckConstraint(PublisherStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint(
            SubmissionMethod.check_constraint("submission_method"), name="submission_method_valid"
        ),
        CheckConstraint(LinkType.check_constraint("link_type"), name="link_type_valid"),
        CheckConstraint(
            f"category IS NULL OR {PublisherCategory.check_constraint('category')}",
            name="category_valid",
        ),
        CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100", name="quality_score_range"
        ),
        CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 100",
            name="relevance_score_range",
        ),
        CheckConstraint(
            "spam_score IS NULL OR spam_score BETWEEN 0 AND 100", name="spam_score_range"
        ),
        CheckConstraint(
            "authority_score IS NULL OR authority_score BETWEEN 0 AND 100",
            name="authority_score_range",
        ),
        CheckConstraint(
            "organic_traffic IS NULL OR organic_traffic >= 0", name="organic_traffic_non_negative"
        ),
        Index("ix_publishers_tenant_id_status", "tenant_id", "status"),
        Index("ix_publishers_tenant_id_pricing_type", "tenant_id", "pricing_type"),
        Index("ix_publishers_tenant_id_category", "tenant_id", "category"),
        Index("ix_publishers_tenant_id_country", "tenant_id", "country"),
        Index("ix_publishers_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_publishers_tenant_id_quality_score", "tenant_id", "quality_score"),
        # The hot path for building a campaign: free, qualified candidates.
        Index(
            "ix_publishers_tenant_id_free_qualified",
            "tenant_id",
            "quality_score",
            postgresql_where=text("pricing_type = 'FREE' AND status = 'QUALIFIED'"),
        ),
        {"comment": "Tenant-owned publisher candidates. RLS protected."},
    )

    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    normalized_domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    #: ISO 3166-1 alpha-2, or NULL for global directories.
    country: Mapped[str | None] = mapped_column(String(2))
    language: Mapped[str | None] = mapped_column(String(8))
    submission_url: Mapped[str | None] = mapped_column(String(2048))
    contact_url: Mapped[str | None] = mapped_column(String(2048))
    submission_method: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{SubmissionMethod.UNKNOWN.value}'")
    )
    #: FREE / PAID / MIXED / UNKNOWN. Only FREE may enter the submission
    #: workflow; the rest are recorded for research and future modules.
    pricing_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{PricingType.UNKNOWN.value}'")
    )
    link_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{LinkType.UNKNOWN.value}'")
    )
    dofollow_supported: Mapped[bool | None] = mapped_column(Boolean)
    nofollow_supported: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{PublisherStatus.DISCOVERED.value}'")
    )
    #: All scores are 0-100. Computed by the qualification service from
    #: configurable weights; never hand-set by a route handler.
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    relevance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    spam_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    authority_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    organic_traffic: Mapped[int | None] = mapped_column(BigInteger)
    #: Raw qualification evidence (HTTP status, detected keywords, provider
    #: metrics). JSONB because the signal set differs per provider and is not
    #: queried relationally.
    signals: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    #: Which discovery run first surfaced this publisher, if any.
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="SET NULL")
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_free(self) -> bool:
        return self.pricing_type == PricingType.FREE.value

    @property
    def is_submittable(self) -> bool:
        """MVP eligibility: free, qualified and not blocked."""
        return self.is_free and self.status == PublisherStatus.QUALIFIED.value


class DiscoveryRun(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """One execution of a publisher-discovery provider.

    Recorded so a discovery is auditable and repeatable: which provider ran,
    with what query, how many results it returned and how many became
    publishers after de-duplication.
    """

    __tablename__ = "discovery_runs"
    __table_args__ = (
        CheckConstraint(DiscoveryRunStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint("results_found >= 0", name="results_found_non_negative"),
        CheckConstraint("publishers_created >= 0", name="publishers_created_non_negative"),
        Index("ix_discovery_runs_tenant_id_status", "tenant_id", "status"),
        Index("ix_discovery_runs_tenant_id_created_at", "tenant_id", "created_at"),
        {"comment": "Tenant-owned publisher discovery executions. RLS protected."},
    )

    campaign_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    #: Provider key, e.g. ``seed_list``, ``search_api``, ``ai``.
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The normalised discovery query (keywords, country, category, limit).
    query: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{DiscoveryRunStatus.PENDING.value}'")
    )
    results_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    publishers_created: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duplicates_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    #: Failure class only — never a provider response body, which could carry
    #: an echoed API key.
    error: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

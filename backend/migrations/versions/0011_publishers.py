"""Publishers and discovery runs.

``uq_publishers_tenant_id_normalized_domain`` is the de-duplication guarantee:
example.com, www.example.com and https://example.com/ all canonicalise to one
row per tenant, so re-running discovery cannot create duplicates.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRICING_TYPES = "'FREE', 'PAID', 'MIXED', 'UNKNOWN'"
_PUBLISHER_STATUSES = "'DISCOVERED', 'QUALIFYING', 'QUALIFIED', 'REJECTED', 'BLOCKED', 'ARCHIVED'"
_SUBMISSION_METHODS = "'MANUAL', 'FORM', 'EMAIL', 'API', 'ACCOUNT_REQUIRED', 'UNKNOWN'"
_LINK_TYPES = "'DOFOLLOW', 'NOFOLLOW', 'MIXED', 'UNKNOWN'"
_CATEGORIES = (
    "'BUSINESS_DIRECTORY', 'LOCAL_DIRECTORY', 'COMPANY_LISTING', 'STARTUP_DIRECTORY', "
    "'SOFTWARE_DIRECTORY', 'INDUSTRY_DIRECTORY', 'ORGANIZATION_LISTING', 'PROFILE_LISTING', "
    "'REVIEW_PLATFORM', 'EVENT_LISTING', 'JOB_BOARD', 'OTHER'"
)


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column(
            "query", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("results_found", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("publishers_created", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicates_skipped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        # Failure class only: never a provider response body, which can echo
        # back the tenant's own API key.
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_discovery_runs"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_discovery_runs_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_discovery_runs_campaign_id_campaigns",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_discovery_runs_status_valid",
        ),
        sa.CheckConstraint(
            "results_found >= 0", name="ck_discovery_runs_results_found_non_negative"
        ),
        sa.CheckConstraint(
            "publishers_created >= 0", name="ck_discovery_runs_publishers_created_non_negative"
        ),
        sa.CheckConstraint(
            "duplicates_skipped >= 0", name="ck_discovery_runs_duplicates_skipped_non_negative"
        ),
        comment="Tenant-owned publisher discovery executions. RLS protected.",
    )
    op.create_index("ix_discovery_runs_tenant_id", "discovery_runs", ["tenant_id"])
    op.create_index("ix_discovery_runs_tenant_id_status", "discovery_runs", ["tenant_id", "status"])
    op.create_index(
        "ix_discovery_runs_tenant_id_created_at", "discovery_runs", ["tenant_id", "created_at"]
    )
    op.execute(
        "CREATE TRIGGER trg_discovery_runs_updated_at BEFORE UPDATE ON discovery_runs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "publishers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("normalized_domain", sa.String(length=253), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("submission_url", sa.String(length=2048), nullable=True),
        sa.Column("contact_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "submission_method",
            sa.String(length=32),
            server_default=sa.text("'UNKNOWN'"),
            nullable=False,
        ),
        sa.Column(
            "pricing_type",
            sa.String(length=16),
            server_default=sa.text("'UNKNOWN'"),
            nullable=False,
        ),
        sa.Column(
            "link_type", sa.String(length=16), server_default=sa.text("'UNKNOWN'"), nullable=False
        ),
        sa.Column("dofollow_supported", sa.Boolean(), nullable=True),
        sa.Column("nofollow_supported", sa.Boolean(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'DISCOVERED'"), nullable=False
        ),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("relevance_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("spam_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("authority_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("organic_traffic", sa.BigInteger(), nullable=True),
        sa.Column(
            "signals", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("discovery_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publishers"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_publishers_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"],
            ["discovery_runs.id"],
            name="fk_publishers_discovery_run_id_discovery_runs",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_domain", name="uq_publishers_tenant_id_normalized_domain"
        ),
        sa.CheckConstraint(
            f"pricing_type IN ({_PRICING_TYPES})", name="ck_publishers_pricing_type_valid"
        ),
        sa.CheckConstraint(f"status IN ({_PUBLISHER_STATUSES})", name="ck_publishers_status_valid"),
        sa.CheckConstraint(
            f"submission_method IN ({_SUBMISSION_METHODS})",
            name="ck_publishers_submission_method_valid",
        ),
        sa.CheckConstraint(f"link_type IN ({_LINK_TYPES})", name="ck_publishers_link_type_valid"),
        sa.CheckConstraint(
            f"category IS NULL OR category IN ({_CATEGORIES})", name="ck_publishers_category_valid"
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100",
            name="ck_publishers_quality_score_range",
        ),
        sa.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 100",
            name="ck_publishers_relevance_score_range",
        ),
        sa.CheckConstraint(
            "spam_score IS NULL OR spam_score BETWEEN 0 AND 100",
            name="ck_publishers_spam_score_range",
        ),
        sa.CheckConstraint(
            "authority_score IS NULL OR authority_score BETWEEN 0 AND 100",
            name="ck_publishers_authority_score_range",
        ),
        sa.CheckConstraint(
            "organic_traffic IS NULL OR organic_traffic >= 0",
            name="ck_publishers_organic_traffic_non_negative",
        ),
        comment="Tenant-owned publisher candidates. RLS protected.",
    )
    op.create_index("ix_publishers_tenant_id", "publishers", ["tenant_id"])
    op.create_index("ix_publishers_normalized_domain", "publishers", ["normalized_domain"])
    op.create_index("ix_publishers_tenant_id_status", "publishers", ["tenant_id", "status"])
    op.create_index(
        "ix_publishers_tenant_id_pricing_type", "publishers", ["tenant_id", "pricing_type"]
    )
    op.create_index("ix_publishers_tenant_id_category", "publishers", ["tenant_id", "category"])
    op.create_index("ix_publishers_tenant_id_country", "publishers", ["tenant_id", "country"])
    op.create_index("ix_publishers_tenant_id_created_at", "publishers", ["tenant_id", "created_at"])
    op.create_index(
        "ix_publishers_tenant_id_quality_score", "publishers", ["tenant_id", "quality_score"]
    )
    # The hot path when assembling a campaign: free, qualified candidates by
    # score. Partial, so rejected/archived rows never enter the index.
    op.create_index(
        "ix_publishers_tenant_id_free_qualified",
        "publishers",
        ["tenant_id", "quality_score"],
        postgresql_where=sa.text("pricing_type = 'FREE' AND status = 'QUALIFIED'"),
    )
    op.execute(
        "CREATE TRIGGER trg_publishers_updated_at BEFORE UPDATE ON publishers "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_publishers_updated_at ON publishers")
    for index in (
        "ix_publishers_tenant_id_free_qualified",
        "ix_publishers_tenant_id_quality_score",
        "ix_publishers_tenant_id_created_at",
        "ix_publishers_tenant_id_country",
        "ix_publishers_tenant_id_category",
        "ix_publishers_tenant_id_pricing_type",
        "ix_publishers_tenant_id_status",
        "ix_publishers_normalized_domain",
        "ix_publishers_tenant_id",
    ):
        op.drop_index(index, table_name="publishers")
    op.drop_table("publishers")

    op.execute("DROP TRIGGER IF EXISTS trg_discovery_runs_updated_at ON discovery_runs")
    for index in (
        "ix_discovery_runs_tenant_id_created_at",
        "ix_discovery_runs_tenant_id_status",
        "ix_discovery_runs_tenant_id",
    ):
        op.drop_index(index, table_name="discovery_runs")
    op.drop_table("discovery_runs")

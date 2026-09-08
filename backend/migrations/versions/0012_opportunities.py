"""Link opportunities.

``uq_opportunities_tenant_campaign_publisher_target`` is the idempotency
guarantee for opportunity creation: a retried request or a repeated discovery
run cannot create a second row for the same campaign/publisher/target-URL.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPPORTUNITY_STATUSES = (
    "'DISCOVERED', 'QUALIFYING', 'QUALIFIED', 'REJECTED', 'SELECTED', 'READY', "
    "'SUBMITTED', 'PUBLISHED', 'FAILED', 'EXPIRED'"
)
_OPPORTUNITY_TYPES = (
    "'FREE_DIRECTORY_LISTING', 'FREE_LOCAL_LISTING', 'FREE_COMPANY_PROFILE', "
    "'FREE_STARTUP_LISTING', 'FREE_SOFTWARE_LISTING', 'FREE_INDUSTRY_LISTING', "
    "'FREE_ORGANIZATION_LISTING', 'FREE_PROFILE_LISTING'"
)


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_type", sa.String(length=48), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("suggested_anchor", sa.String(length=255), nullable=True),
        sa.Column("suggested_title", sa.String(length=255), nullable=True),
        sa.Column("suggested_description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'DISCOVERED'"), nullable=False
        ),
        sa.Column("qualification_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("50"), nullable=False),
        # Snapshot of the publisher's submission URL at qualification time, so
        # a later publisher edit cannot silently retarget queued work.
        sa.Column("submission_url", sa.String(length=2048), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_opportunities"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_opportunities_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_opportunities_campaign_id_campaigns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["publisher_id"],
            ["publishers.id"],
            name="fk_opportunities_publisher_id_publishers",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "campaign_id",
            "publisher_id",
            "target_url",
            name="uq_opportunities_tenant_campaign_publisher_target",
        ),
        sa.CheckConstraint(
            f"status IN ({_OPPORTUNITY_STATUSES})", name="ck_opportunities_status_valid"
        ),
        sa.CheckConstraint(
            f"opportunity_type IN ({_OPPORTUNITY_TYPES})",
            name="ck_opportunities_opportunity_type_valid",
        ),
        sa.CheckConstraint(
            "qualification_score IS NULL OR qualification_score BETWEEN 0 AND 100",
            name="ck_opportunities_qualification_score_range",
        ),
        sa.CheckConstraint("priority BETWEEN 0 AND 100", name="ck_opportunities_priority_range"),
        comment="Tenant-owned listing opportunities. RLS protected.",
    )
    op.create_index("ix_opportunities_tenant_id", "opportunities", ["tenant_id"])
    op.create_index("ix_opportunities_tenant_id_status", "opportunities", ["tenant_id", "status"])
    op.create_index(
        "ix_opportunities_tenant_id_campaign_id", "opportunities", ["tenant_id", "campaign_id"]
    )
    op.create_index(
        "ix_opportunities_tenant_id_publisher_id", "opportunities", ["tenant_id", "publisher_id"]
    )
    op.create_index(
        "ix_opportunities_tenant_id_created_at", "opportunities", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_opportunities_tenant_id_updated_at", "opportunities", ["tenant_id", "updated_at"]
    )
    # The specialist work queue. Partial so it stays small as PUBLISHED rows
    # accumulate into the hundreds of thousands.
    op.create_index(
        "ix_opportunities_tenant_id_workqueue",
        "opportunities",
        ["tenant_id", "campaign_id", "priority"],
        postgresql_where=sa.text("status IN ('QUALIFIED', 'SELECTED', 'READY')"),
    )
    op.execute(
        "CREATE TRIGGER trg_opportunities_updated_at BEFORE UPDATE ON opportunities "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_opportunities_updated_at ON opportunities")
    for index in (
        "ix_opportunities_tenant_id_workqueue",
        "ix_opportunities_tenant_id_updated_at",
        "ix_opportunities_tenant_id_created_at",
        "ix_opportunities_tenant_id_publisher_id",
        "ix_opportunities_tenant_id_campaign_id",
        "ix_opportunities_tenant_id_status",
        "ix_opportunities_tenant_id",
    ):
        op.drop_index(index, table_name="opportunities")
    op.drop_table("opportunities")

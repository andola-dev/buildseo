"""Campaigns.

``ck_campaigns_mvp_free_only`` pins ``free_only`` true in the database. This
platform builds free listings only; paid placements are out of scope. Adding
paid support later means dropping exactly one named constraint in a migration —
a deliberate, reviewable decision rather than an accident.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_website_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'DRAFT'"), nullable=False
        ),
        sa.Column("target_country", sa.String(length=2), nullable=True),
        sa.Column("target_language", sa.String(length=8), nullable=True),
        # Planning/reporting only: nothing in this platform spends a budget.
        sa.Column("budget", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("free_only", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("target_link_count", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_campaigns"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_campaigns_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["client_website_id"],
            ["client_websites.id"],
            name="fk_campaigns_client_website_id_client_websites",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "client_website_id", "name", name="uq_campaigns_tenant_website_name"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED')",
            name="ck_campaigns_status_valid",
        ),
        sa.CheckConstraint("free_only", name="ck_campaigns_mvp_free_only"),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_campaigns_date_range_ordered",
        ),
        sa.CheckConstraint(
            "budget IS NULL OR budget >= 0", name="ck_campaigns_budget_non_negative"
        ),
        sa.CheckConstraint(
            "target_link_count IS NULL OR target_link_count > 0",
            name="ck_campaigns_target_link_count_positive",
        ),
        comment="Tenant-owned campaigns. free_only is pinned true for the MVP.",
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])
    op.create_index("ix_campaigns_tenant_id_status", "campaigns", ["tenant_id", "status"])
    op.create_index(
        "ix_campaigns_tenant_id_client_website_id", "campaigns", ["tenant_id", "client_website_id"]
    )
    op.create_index("ix_campaigns_tenant_id_created_at", "campaigns", ["tenant_id", "created_at"])
    op.execute(
        "CREATE TRIGGER trg_campaigns_updated_at BEFORE UPDATE ON campaigns "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_campaigns_updated_at ON campaigns")
    op.drop_index("ix_campaigns_tenant_id_created_at", table_name="campaigns")
    op.drop_index("ix_campaigns_tenant_id_client_website_id", table_name="campaigns")
    op.drop_index("ix_campaigns_tenant_id_status", table_name="campaigns")
    op.drop_index("ix_campaigns_tenant_id", table_name="campaigns")
    op.drop_table("campaigns")

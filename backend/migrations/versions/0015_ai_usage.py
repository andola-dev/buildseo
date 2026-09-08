"""AI usage ledger.

Append-only, and deliberately stores no prompt or completion text: the accepted
output already lives in ``generated_contents`` where a human reviews it, and
duplicating prompts here would multiply tenant business data at rest for no
accounting benefit. Provider keys are never recorded.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=48), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        # An application-side estimate, not a provider invoice.
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'SUCCEEDED'"), nullable=False
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_records"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_ai_usage_records_tenant_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "operation IN ('generate', 'embed')", name="ck_ai_usage_records_operation_valid"
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'FAILED')", name="ck_ai_usage_records_status_valid"
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_ai_usage_records_input_tokens_valid",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_ai_usage_records_output_tokens_valid",
        ),
        sa.CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_ai_usage_records_estimated_cost_valid",
        ),
        comment="Tenant-owned AI usage ledger. Append-only; stores no prompts.",
    )
    op.create_index("ix_ai_usage_records_tenant_id", "ai_usage_records", ["tenant_id"])
    op.create_index("ix_ai_usage_records_request_id", "ai_usage_records", ["request_id"])
    # Drives per-tenant usage dashboards and cost rollups.
    op.create_index(
        "ix_ai_usage_records_tenant_id_created_at", "ai_usage_records", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_ai_usage_records_tenant_id_provider_model",
        "ai_usage_records",
        ["tenant_id", "provider", "model"],
    )
    op.create_index(
        "ix_ai_usage_records_tenant_id_operation", "ai_usage_records", ["tenant_id", "operation"]
    )


def downgrade() -> None:
    for index in (
        "ix_ai_usage_records_tenant_id_operation",
        "ix_ai_usage_records_tenant_id_provider_model",
        "ix_ai_usage_records_tenant_id_created_at",
        "ix_ai_usage_records_request_id",
        "ix_ai_usage_records_tenant_id",
    ):
        op.drop_index(index, table_name="ai_usage_records")
    op.drop_table("ai_usage_records")

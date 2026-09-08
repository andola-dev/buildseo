"""Client websites — the sites a tenant builds links for.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_websites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        # Canonical de-duplication identity produced by normalize_domain().
        sa.Column("normalized_domain", sa.String(length=253), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("target_country", sa.String(length=2), nullable=True),
        sa.Column(
            "target_countries",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("target_language", sa.String(length=8), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_client_websites"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_client_websites_tenant_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_domain", name="uq_client_websites_tenant_id_normalized_domain"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name="ck_client_websites_status_valid"
        ),
        comment="Tenant-owned client sites. RLS protected.",
    )
    op.create_index("ix_client_websites_tenant_id", "client_websites", ["tenant_id"])
    op.create_index(
        "ix_client_websites_normalized_domain", "client_websites", ["normalized_domain"]
    )
    op.create_index("ix_client_websites_industry", "client_websites", ["industry"])
    op.create_index(
        "ix_client_websites_tenant_id_status", "client_websites", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_client_websites_tenant_id_created_at", "client_websites", ["tenant_id", "created_at"]
    )
    op.execute(
        "CREATE TRIGGER trg_client_websites_updated_at BEFORE UPDATE ON client_websites "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_client_websites_updated_at ON client_websites")
    op.drop_index("ix_client_websites_tenant_id_created_at", table_name="client_websites")
    op.drop_index("ix_client_websites_tenant_id_status", table_name="client_websites")
    op.drop_index("ix_client_websites_industry", table_name="client_websites")
    op.drop_index("ix_client_websites_normalized_domain", table_name="client_websites")
    op.drop_index("ix_client_websites_tenant_id", table_name="client_websites")
    op.drop_table("client_websites")

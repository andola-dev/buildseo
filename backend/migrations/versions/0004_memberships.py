"""Tenant memberships.

The sole authority on tenant access. A user may hold memberships in many
tenants, which is why the access token carries only a currently-selected
tenant and re-validates it here on every request.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
        sa.Column("is_owner", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_tenant_memberships"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tenant_memberships_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_id_user_id"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INVITED', 'SUSPENDED', 'REMOVED')",
            name="ck_tenant_memberships_status_valid",
        ),
        comment="Tenant access grants. RLS: tenant match OR own user_id.",
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    # Answers "which tenants may this user enter?" without a tenant context.
    op.create_index(
        "ix_tenant_memberships_user_id_status", "tenant_memberships", ["user_id", "status"]
    )
    op.create_index(
        "ix_tenant_memberships_tenant_id_owner",
        "tenant_memberships",
        ["tenant_id"],
        postgresql_where=sa.text("is_owner"),
    )
    op.execute(
        "CREATE TRIGGER trg_tenant_memberships_updated_at BEFORE UPDATE ON tenant_memberships "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tenant_memberships_updated_at ON tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id_owner", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_user_id_status", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")

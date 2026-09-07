"""Per-tenant roles.

Each tenant gets its own copy of the five system roles at creation time, so a
workspace can edit or extend its roles without affecting anyone else. Custom
roles are simply rows with ``is_system = false`` — no schema change needed.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_roles_tenant_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_id_slug"),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9_]{1,62}[a-z0-9]$'", name="ck_roles_slug_format"
        ),
        comment="Per-tenant roles. System roles are seeded and protected.",
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])
    op.create_index("ix_roles_tenant_id_is_system", "roles", ["tenant_id", "is_system"])
    op.execute(
        "CREATE TRIGGER trg_roles_updated_at BEFORE UPDATE ON roles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_roles_updated_at ON roles")
    op.drop_index("ix_roles_tenant_id_is_system", table_name="roles")
    op.drop_index("ix_roles_tenant_id", table_name="roles")
    op.drop_table("roles")

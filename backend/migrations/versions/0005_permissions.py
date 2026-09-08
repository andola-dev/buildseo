"""Global permission catalog.

Permissions are platform-wide and seeded, not tenant-owned: a code must mean
the same thing in every workspace, and letting tenants mint codes would make
authorisation unreviewable. Tenants compose them into roles instead.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
        sa.UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),
        # Keeps the denormalised code and its parts from drifting apart.
        sa.CheckConstraint(
            "code = resource || '.' || action", name="ck_permissions_code_matches_parts"
        ),
        comment="Global permission catalog. Seeded, not tenant-owned.",
    )
    op.create_index("ix_permissions_resource", "permissions", ["resource"])


def downgrade() -> None:
    op.drop_index("ix_permissions_resource", table_name="permissions")
    op.drop_table("permissions")

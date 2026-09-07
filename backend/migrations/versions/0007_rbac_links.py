"""RBAC link tables: role→permission and membership→role.

Both carry ``tenant_id`` even though it is derivable from their parent row.
That is deliberate: an RLS policy needs a local discriminator column, and
duplicating it keeps the policy a single indexed comparison instead of a
correlated subquery evaluated on every read.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_role_permissions"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_role_permissions_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        comment="Role-to-permission grants.",
    )
    op.create_index("ix_role_permissions_tenant_id", "role_permissions", ["tenant_id"])
    op.create_index(
        "ix_role_permissions_tenant_id_role_id", "role_permissions", ["tenant_id", "role_id"]
    )

    op.create_table(
        "membership_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_membership_roles"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_membership_roles_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["tenant_memberships.id"],
            name="fk_membership_roles_membership_id_tenant_memberships",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_membership_roles_role_id_roles", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("membership_id", "role_id", name="uq_membership_roles_membership_role"),
        comment="Role assignments per tenant membership.",
    )
    op.create_index("ix_membership_roles_tenant_id", "membership_roles", ["tenant_id"])
    op.create_index(
        "ix_membership_roles_tenant_id_membership_id",
        "membership_roles",
        ["tenant_id", "membership_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_membership_roles_tenant_id_membership_id", table_name="membership_roles")
    op.drop_index("ix_membership_roles_tenant_id", table_name="membership_roles")
    op.drop_table("membership_roles")
    op.drop_index("ix_role_permissions_tenant_id_role_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_tenant_id", table_name="role_permissions")
    op.drop_table("role_permissions")

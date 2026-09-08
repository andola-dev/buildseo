"""Refresh sessions (token families).

Stores only a SHA-256 digest of each refresh token. Not tenant-owned: token
refresh happens before a tenant is selected.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Hex SHA-256. Unique so the same digest can never live in two rows.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("active_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["active_tenant_id"],
            ["tenants.id"],
            name="fk_refresh_sessions_active_tenant_id_tenants",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        sa.CheckConstraint("length(token_hash) = 64", name="ck_refresh_sessions_token_hash_length"),
        comment="Refresh token families. Stores digests only, never tokens.",
    )
    op.create_index(
        "ix_refresh_sessions_user_id_revoked", "refresh_sessions", ["user_id", "revoked"]
    )
    # Reuse detection revokes an entire family in one statement.
    op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])
    # Supports the expired-session reaper without scanning revoked history.
    op.create_index(
        "ix_refresh_sessions_expires_at_live",
        "refresh_sessions",
        ["expires_at"],
        postgresql_where=sa.text("NOT revoked"),
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_expires_at_live", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id_revoked", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")

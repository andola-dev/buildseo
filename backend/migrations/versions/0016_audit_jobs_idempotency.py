"""Audit logs, background jobs and idempotency keys.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------- audit logs
    # Append-only: no updated_at, no update path, no delete endpoint, so the
    # trail cannot be quietly rewritten. ``metadata`` is built from per-action
    # allow-lists in the audit service, never from a raw request body.
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_audit_logs_tenant_id", ondelete="CASCADE"
        ),
        # SET NULL: the record of an action outlives the account that did it.
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_audit_logs_user_id_users", ondelete="SET NULL"
        ),
        comment="Tenant-owned append-only audit trail. RLS protected.",
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_tenant_id_created_at", "audit_logs", ["tenant_id", "created_at"])
    op.create_index("ix_audit_logs_tenant_id_action", "audit_logs", ["tenant_id", "action"])
    op.create_index("ix_audit_logs_tenant_id_user_id", "audit_logs", ["tenant_id", "user_id"])
    op.create_index(
        "ix_audit_logs_tenant_id_resource",
        "audit_logs",
        ["tenant_id", "resource_type", "resource_id"],
    )

    # ------------------------------------------------------------------- jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column(
            "run_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("enqueued_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_jobs_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["enqueued_by_user_id"],
            ["users.id"],
            name="fk_jobs_enqueued_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_jobs_status_valid",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts_positive"),
        comment="Tenant-owned background jobs. Claimed with FOR UPDATE SKIP LOCKED.",
    )
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])
    # The claim query's index: due, pending work, oldest first. Partial so it
    # does not grow with completed history.
    op.create_index(
        "ix_jobs_claimable",
        "jobs",
        ["run_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index("ix_jobs_tenant_id_status", "jobs", ["tenant_id", "status"])
    op.create_index("ix_jobs_tenant_id_created_at", "jobs", ["tenant_id", "created_at"])
    op.create_index("ix_jobs_task_name_status", "jobs", ["task_name", "status"])
    op.execute(
        "CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # ------------------------------------------------------- idempotency keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        # Digest of the canonicalised request body: reusing a key with a
        # different body is a client bug, and is rejected rather than replayed.
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_idempotency_keys_tenant_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "key", "endpoint", name="uq_idempotency_keys_tenant_key_endpoint"
        ),
        comment="Tenant-owned idempotency ledger for unsafe operations.",
    )
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])
    # Supports the retention sweep that expires old keys.
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_tenant_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.execute("DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs")
    for index in (
        "ix_jobs_task_name_status",
        "ix_jobs_tenant_id_created_at",
        "ix_jobs_tenant_id_status",
        "ix_jobs_claimable",
        "ix_jobs_tenant_id",
    ):
        op.drop_index(index, table_name="jobs")
    op.drop_table("jobs")

    for index in (
        "ix_audit_logs_tenant_id_resource",
        "ix_audit_logs_tenant_id_user_id",
        "ix_audit_logs_tenant_id_action",
        "ix_audit_logs_tenant_id_created_at",
        "ix_audit_logs_tenant_id",
    ):
        op.drop_index(index, table_name="audit_logs")
    op.drop_table("audit_logs")

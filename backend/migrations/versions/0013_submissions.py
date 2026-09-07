"""Submissions and AI-generated listing content.

Two guarantees are enforced here rather than left to application code:

* ``enforce_submission_free_only`` — a trigger that refuses any submission
  whose opportunity points at a publisher that is not ``pricing_type = FREE``.
  Business rules 1 and 2 are the whole point of this product; a service-layer
  check alone would let a future bug (or a direct SQL fix) violate them.
* ``ck_submissions_submitted_requires_approval`` — the human-in-the-loop gate.
  A submission cannot sit in SUBMITTED or beyond without the approving user and
  timestamp that authorised it.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUBMISSION_STATUSES = (
    "'READY', 'IN_PROGRESS', 'SUBMITTED', 'PENDING_APPROVAL', 'PUBLISHED', "
    "'VERIFICATION_PENDING', 'VERIFIED', 'REJECTED', 'FAILED'"
)
_SUBMISSION_METHODS = "'MANUAL', 'FORM', 'EMAIL', 'API', 'ACCOUNT_REQUIRED', 'UNKNOWN'"
_CONTENT_STATUSES = "'DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'SUPERSEDED'"
_POST_APPROVAL_STATUSES = "'SUBMITTED', 'PUBLISHED', 'VERIFICATION_PENDING', 'VERIFIED'"


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'READY'"), nullable=False
        ),
        sa.Column("submitted_url", sa.String(length=2048), nullable=True),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("anchor_text", sa.String(length=255), nullable=True),
        sa.Column("submitted_title", sa.String(length=255), nullable=True),
        sa.Column("submitted_description", sa.Text(), nullable=True),
        sa.Column(
            "submission_method",
            sa.String(length=32),
            server_default=sa.text("'MANUAL'"),
            nullable=False,
        ),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "verification_evidence",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_submissions_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_submissions_campaign_id_campaigns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name="fk_submissions_opportunity_id_opportunities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_submissions_approved_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"status IN ({_SUBMISSION_STATUSES})", name="ck_submissions_status_valid"
        ),
        sa.CheckConstraint(
            f"submission_method IN ({_SUBMISSION_METHODS})",
            name="ck_submissions_submission_method_valid",
        ),
        sa.CheckConstraint(
            f"status NOT IN ({_POST_APPROVAL_STATUSES}) "
            "OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_submissions_submitted_requires_approval",
        ),
        comment="Tenant-owned submissions. FREE-only, approval-gated, RLS protected.",
    )
    op.create_index("ix_submissions_tenant_id", "submissions", ["tenant_id"])
    # One live submission per opportunity; terminal rows excluded so a failed
    # attempt can be retried without losing its history.
    op.create_index(
        "uq_submissions_tenant_id_opportunity_id_live",
        "submissions",
        ["tenant_id", "opportunity_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('REJECTED', 'FAILED')"),
    )
    op.create_index("ix_submissions_tenant_id_status", "submissions", ["tenant_id", "status"])
    op.create_index(
        "ix_submissions_tenant_id_campaign_id", "submissions", ["tenant_id", "campaign_id"]
    )
    op.create_index(
        "ix_submissions_tenant_id_created_at", "submissions", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_submissions_tenant_id_awaiting_review",
        "submissions",
        ["tenant_id", "updated_at"],
        postgresql_where=sa.text("status = 'PENDING_APPROVAL'"),
    )
    op.execute(
        "CREATE TRIGGER trg_submissions_updated_at BEFORE UPDATE ON submissions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # ---------------------------------------------------------------- rule 1/2
    # Only FREE publishers may enter the submission workflow. Enforced in the
    # database so the invariant survives an application bug or a manual fix.
    op.execute("""
        -- Deliberately NOT security definer: the lookup below runs with the
        -- caller's privileges and therefore under the caller's RLS policies.
        -- That makes it fail closed -- if the opportunity or publisher is not
        -- visible in the current tenant context, publisher_pricing comes back
        -- NULL and the insert is rejected rather than silently permitted.
        CREATE OR REPLACE FUNCTION enforce_submission_free_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            publisher_pricing text;
        BEGIN
            SELECT p.pricing_type
              INTO publisher_pricing
              FROM opportunities o
              JOIN publishers p ON p.id = o.publisher_id
             WHERE o.id = NEW.opportunity_id;

            IF publisher_pricing IS NULL THEN
                RAISE EXCEPTION
                    'submission % references an opportunity whose publisher is not '
                    'visible in the current tenant context', NEW.id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            IF publisher_pricing <> 'FREE' THEN
                RAISE EXCEPTION
                    'only FREE publishers may enter the submission workflow (got %)',
                    publisher_pricing
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END
        $$
        """)
    op.execute("""
        CREATE TRIGGER trg_submissions_free_only
        BEFORE INSERT OR UPDATE OF opportunity_id ON submissions
        FOR EACH ROW EXECUTE FUNCTION enforce_submission_free_only()
        """)

    op.create_table(
        "generated_contents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "content_status",
            sa.String(length=32),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column(
            "generated_content",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ai_provider", sa.String(length=64), nullable=True),
        sa.Column("ai_model", sa.String(length=120), nullable=True),
        sa.Column("generation_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_generated_contents"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_generated_contents_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name="fk_generated_contents_opportunity_id_opportunities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name="fk_generated_contents_reviewed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"content_status IN ({_CONTENT_STATUSES})", name="ck_generated_contents_status_valid"
        ),
        comment="Tenant-owned AI listing drafts awaiting human review. RLS protected.",
    )
    op.create_index("ix_generated_contents_tenant_id", "generated_contents", ["tenant_id"])
    op.create_index(
        "ix_generated_contents_tenant_id_opportunity_id",
        "generated_contents",
        ["tenant_id", "opportunity_id"],
    )
    op.create_index(
        "ix_generated_contents_tenant_id_content_status",
        "generated_contents",
        ["tenant_id", "content_status"],
    )
    op.create_index(
        "ix_generated_contents_tenant_id_created_at",
        "generated_contents",
        ["tenant_id", "created_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_generated_contents_updated_at BEFORE UPDATE ON generated_contents "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_generated_contents_updated_at ON generated_contents")
    for index in (
        "ix_generated_contents_tenant_id_created_at",
        "ix_generated_contents_tenant_id_content_status",
        "ix_generated_contents_tenant_id_opportunity_id",
        "ix_generated_contents_tenant_id",
    ):
        op.drop_index(index, table_name="generated_contents")
    op.drop_table("generated_contents")

    op.execute("DROP TRIGGER IF EXISTS trg_submissions_free_only ON submissions")
    op.execute("DROP FUNCTION IF EXISTS enforce_submission_free_only()")
    op.execute("DROP TRIGGER IF EXISTS trg_submissions_updated_at ON submissions")
    for index in (
        "ix_submissions_tenant_id_awaiting_review",
        "ix_submissions_tenant_id_created_at",
        "ix_submissions_tenant_id_campaign_id",
        "ix_submissions_tenant_id_status",
        "uq_submissions_tenant_id_opportunity_id_live",
        "ix_submissions_tenant_id",
    ):
        op.drop_index(index, table_name="submissions")
    op.drop_table("submissions")

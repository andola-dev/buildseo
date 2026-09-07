"""Submissions and the AI-generated content reviewed before they are sent."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ContentStatus, SubmissionMethod, SubmissionStatus


class Submission(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """The record of submitting one opportunity to one publisher.

    A submission may only exist for an opportunity whose publisher is
    ``pricing_type = FREE``. That is checked by the service *and* by a database
    trigger (``enforce_submission_free_only``), because a business rule this
    central should not depend on application code being correct.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        # One live submission per opportunity. Terminal rows are excluded so a
        # rejected or failed attempt can be retried with a fresh row while the
        # history is preserved.
        Index(
            "uq_submissions_tenant_id_opportunity_id_live",
            "tenant_id",
            "opportunity_id",
            unique=True,
            postgresql_where=text("status NOT IN ('REJECTED', 'FAILED')"),
        ),
        CheckConstraint(SubmissionStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint(
            SubmissionMethod.check_constraint("submission_method"), name="submission_method_valid"
        ),
        # Human-in-the-loop gate: anything at or past SUBMITTED must carry the
        # approval that authorised it.
        CheckConstraint(
            "status NOT IN ('SUBMITTED', 'PUBLISHED', 'VERIFICATION_PENDING', 'VERIFIED') "
            "OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="submitted_requires_approval",
        ),
        Index("ix_submissions_tenant_id_status", "tenant_id", "status"),
        Index("ix_submissions_tenant_id_campaign_id", "tenant_id", "campaign_id"),
        Index("ix_submissions_tenant_id_created_at", "tenant_id", "created_at"),
        Index(
            "ix_submissions_tenant_id_awaiting_review",
            "tenant_id",
            "updated_at",
            postgresql_where=text("status = 'PENDING_APPROVAL'"),
        ),
        {"comment": "Tenant-owned submissions. FREE-only, approval-gated, RLS protected."},
    )

    campaign_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{SubmissionStatus.READY.value}'")
    )
    #: Where the listing was actually submitted (the publisher's form URL).
    submitted_url: Mapped[str | None] = mapped_column(String(2048))
    #: The client URL that was listed.
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    anchor_text: Mapped[str | None] = mapped_column(String(255))
    submitted_title: Mapped[str | None] = mapped_column(String(255))
    submitted_description: Mapped[str | None] = mapped_column(Text)
    submission_method: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{SubmissionMethod.MANUAL.value}'")
    )
    #: Who approved the submission. Required before it can leave the review gate.
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Failure class or the publisher's stated reason. Never a raw HTTP body.
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    #: Evidence captured during verification (HTTP status, whether the target
    #: link was found, rel attribute observed).
    verification_evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class GeneratedContent(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """AI-drafted listing copy, always persisted *before* submission.

    Storing the draft with its provider, model and timestamp is what makes the
    human-in-the-loop workflow auditable: a reviewer approves a specific
    artifact, and later anyone can see exactly what was generated, by what, and
    who signed it off. Prompts are not stored — only the output.
    """

    __tablename__ = "generated_contents"
    __table_args__ = (
        CheckConstraint(ContentStatus.check_constraint("content_status"), name="status_valid"),
        Index("ix_generated_contents_tenant_id_opportunity_id", "tenant_id", "opportunity_id"),
        Index("ix_generated_contents_tenant_id_content_status", "tenant_id", "content_status"),
        Index("ix_generated_contents_tenant_id_created_at", "tenant_id", "created_at"),
        {"comment": "Tenant-owned AI listing drafts awaiting human review. RLS protected."},
    )

    opportunity_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    content_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{ContentStatus.DRAFT.value}'")
    )
    #: The generated fields: listing_title, short_description, long_description,
    #: business_description, category_suggestion, anchor_suggestion, target_url,
    #: tags. JSONB because the field set evolves with the prompt templates and
    #: is only ever read as a whole document.
    generated_content: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ai_provider: Mapped[str | None] = mapped_column(String(64))
    ai_model: Mapped[str | None] = mapped_column(String(120))
    generation_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

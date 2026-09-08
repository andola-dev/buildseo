"""Opportunity and generated-content schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.core.domains import normalize_url
from app.core.enums import ContentStatus, OpportunityStatus, OpportunityType, PublisherCategory
from app.core.exceptions import ValidationError as DomainValidationError
from app.schemas.common import ReadSchemaBase, SchemaBase


class OpportunityCreate(SchemaBase):
    """Create an opportunity for a campaign and publisher.

    Retrying this call with the same campaign, publisher and target URL returns
    the existing row rather than creating a duplicate — the unique constraint
    ``uq_opportunities_tenant_campaign_publisher_target`` backs that guarantee.
    """

    campaign_id: UUID
    publisher_id: UUID
    opportunity_type: OpportunityType = Field(default=OpportunityType.FREE_DIRECTORY_LISTING)
    target_url: str = Field(max_length=2048, description="Client URL to be listed")
    suggested_anchor: str | None = Field(default=None, max_length=255)
    suggested_title: str | None = Field(default=None, max_length=255)
    suggested_description: str | None = Field(default=None, max_length=5000)
    category: PublisherCategory | None = None
    priority: int = Field(default=50, ge=0, le=100)

    @field_validator("target_url")
    @classmethod
    def _normalize(cls, value: str) -> str:
        try:
            return normalize_url(value)
        except DomainValidationError as exc:
            raise ValueError(exc.message) from exc


class OpportunityUpdate(SchemaBase):
    """Partial update.

    ``status`` is absent on purpose: lifecycle changes go through the explicit
    transition endpoints (``/qualify``, ``/select``, ``/reject``) so every move
    is validated against the state machine and audited.
    """

    suggested_anchor: str | None = Field(default=None, max_length=255)
    suggested_title: str | None = Field(default=None, max_length=255)
    suggested_description: str | None = Field(default=None, max_length=5000)
    category: PublisherCategory | None = None
    priority: int | None = Field(default=None, ge=0, le=100)


class OpportunityRead(ReadSchemaBase):
    id: UUID
    campaign_id: UUID
    publisher_id: UUID
    opportunity_type: str
    target_url: str
    suggested_anchor: str | None = None
    suggested_title: str | None = None
    suggested_description: str | None = None
    category: str | None = None
    status: str
    qualification_score: float | None = None
    priority: int
    submission_url: str | None = None
    rejection_reason: str | None = None
    discovered_at: datetime | None = None
    qualified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpportunityTransitionRequest(SchemaBase):
    """Advance an opportunity to a specific status."""

    target_status: OpportunityStatus
    reason: str | None = Field(default=None, max_length=255, description="Required when rejecting")


class OpportunityRejectRequest(SchemaBase):
    reason: str = Field(min_length=3, max_length=255)


class ContentGenerationRequest(SchemaBase):
    """Ask the tenant's configured AI provider for listing copy.

    Which provider runs is not a parameter: it comes from the tenant's
    ``content_generation`` configuration, so the caller never names a vendor.
    """

    tone: str | None = Field(
        default=None, max_length=64, description="e.g. professional, friendly, technical"
    )
    keywords: list[str] = Field(default_factory=list, max_length=20)
    max_description_words: int = Field(default=120, ge=20, le=600)
    include_short_description: bool = Field(default=True)
    include_long_description: bool = Field(default=True)
    regenerate: bool = Field(
        default=False,
        description="Supersede existing drafts and produce a new one for review",
    )


class GeneratedContentRead(ReadSchemaBase):
    """An AI draft awaiting or holding a review decision.

    Always persisted before a submission is sent, so a reviewer approves a
    concrete artifact and an auditor can see exactly what was generated, by
    which model, and who signed it off.
    """

    id: UUID
    opportunity_id: UUID
    content_status: str
    generated_content: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Generated fields: listing_title, short_description, long_description, "
            "business_description, category_suggestion, anchor_suggestion, target_url, tags."
        ),
    )
    ai_provider: str | None = None
    ai_model: str | None = None
    generation_timestamp: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ContentReviewRequest(SchemaBase):
    """The human decision on a draft."""

    decision: ContentStatus = Field(description="APPROVED or REJECTED")
    notes: str | None = Field(default=None, max_length=2000)
    edited_content: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Reviewer's corrections, stored in place of the generated values. The "
            "original remains in the superseded draft history."
        ),
    )

    @field_validator("decision")
    @classmethod
    def _only_terminal_decisions(cls, value: ContentStatus) -> ContentStatus:
        if value not in (ContentStatus.APPROVED, ContentStatus.REJECTED):
            raise ValueError("decision must be APPROVED or REJECTED")
        return value

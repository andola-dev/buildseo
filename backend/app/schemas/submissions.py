"""Submission schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.core.domains import normalize_url
from app.core.enums import SubmissionMethod, SubmissionStatus
from app.core.exceptions import ValidationError as DomainValidationError
from app.schemas.common import ReadSchemaBase, SchemaBase


class SubmissionCreate(SchemaBase):
    """Prepare a submission for an opportunity.

    The publisher must be ``pricing_type = FREE``; anything else is refused by
    the service and, independently, by a database trigger. The submission
    starts in a pre-approval state — creating one never sends anything.
    """

    opportunity_id: UUID
    anchor_text: str | None = Field(default=None, max_length=255)
    submitted_title: str | None = Field(default=None, max_length=255)
    submitted_description: str | None = Field(default=None, max_length=5000)
    submission_method: SubmissionMethod | None = Field(
        default=None,
        description="Defaults to the publisher's recorded method, or MANUAL when unknown",
    )
    notes: str | None = Field(default=None, max_length=5000)
    use_approved_content: bool = Field(
        default=True,
        description=(
            "Populate title/description from the opportunity's approved AI draft. "
            "When false, the values supplied here are used verbatim."
        ),
    )


class SubmissionUpdate(SchemaBase):
    """Edit a submission's payload before it is sent.

    ``status`` is absent: transitions go through ``/approve``, ``/execute``,
    ``/verify`` and ``/transition`` so each one is validated against the state
    machine and recorded in the audit trail.
    """

    anchor_text: str | None = Field(default=None, max_length=255)
    submitted_title: str | None = Field(default=None, max_length=255)
    submitted_description: str | None = Field(default=None, max_length=5000)
    submission_method: SubmissionMethod | None = None
    notes: str | None = Field(default=None, max_length=5000)


class SubmissionRead(ReadSchemaBase):
    id: UUID
    campaign_id: UUID
    opportunity_id: UUID
    status: str
    submitted_url: str | None = None
    target_url: str
    anchor_text: str | None = None
    submitted_title: str | None = None
    submitted_description: str | None = None
    submission_method: str
    approved_by_user_id: UUID | None = Field(
        default=None, description="Who authorised sending this submission"
    )
    approved_at: datetime | None = None
    submitted_at: datetime | None = None
    published_at: datetime | None = None
    verified_at: datetime | None = None
    failure_reason: str | None = None
    notes: str | None = None
    verification_evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SubmissionApproveRequest(SchemaBase):
    """Record the human approval that unlocks sending.

    Held behind its own permission (``submission.approve``) so a specialist can
    prepare work without being able to authorise it.
    """

    notes: str | None = Field(default=None, max_length=2000)


class SubmissionExecuteRequest(SchemaBase):
    """Record or perform the actual submission."""

    submitted_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Where the listing was submitted; defaults to the publisher's submission URL",
    )
    mark_published: bool = Field(
        default=False,
        description="Set when the publisher confirmed publication immediately",
    )
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("submitted_url")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return normalize_url(value)
        except DomainValidationError as exc:
            raise ValueError(exc.message) from exc


class SubmissionVerifyRequest(SchemaBase):
    """Check that the published listing really carries the link."""

    published_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Live page to inspect; defaults to the recorded submitted_url",
    )
    fetch_live: bool = Field(
        default=True, description="Fetch the page. When false, record the manual outcome below."
    )
    manual_result: bool | None = Field(
        default=None, description="Verification outcome when fetch_live is false"
    )

    @field_validator("published_url")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return normalize_url(value)
        except DomainValidationError as exc:
            raise ValueError(exc.message) from exc


class SubmissionTransitionRequest(SchemaBase):
    """Escape hatch for an explicit, still-validated status move."""

    target_status: SubmissionStatus
    reason: str | None = Field(default=None, max_length=500)


class SubmissionStateMachineRead(ReadSchemaBase):
    """The allowed transitions, so a client can render the right actions."""

    statuses: list[str]
    transitions: dict[str, list[str]]
    terminal_statuses: list[str]
    approval_required_for: list[str]

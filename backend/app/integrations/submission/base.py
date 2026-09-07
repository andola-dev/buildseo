"""The submission contract.

Submitting a listing is the one place where this platform touches a third
party's system on a tenant's behalf, so the contract is written around what it
will refuse to do.

A provider may decline by returning ``BLOCKED_REQUIRES_MANUAL`` rather than
raising. That outcome is a first-class, expected result: the workflow records
it and routes the submission to a human. There is deliberately no mechanism —
and no configuration flag — for solving a CAPTCHA, defeating an anti-bot
challenge, or working around a publisher's stated restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SubmissionOutcomeStatus(StrEnum):
    """What happened when a submission was attempted."""

    #: Recorded for a human to perform, or performed by one.
    RECORDED = "RECORDED"
    #: Delivered to the publisher.
    SUBMITTED = "SUBMITTED"
    #: The publisher confirmed publication immediately.
    PUBLISHED = "PUBLISHED"
    #: The target requires a human. Not an error: the expected result whenever
    #: a CAPTCHA, an anti-bot challenge, a login or a ToS restriction is
    #: present. The workflow falls back to manual submission.
    BLOCKED_REQUIRES_MANUAL = "BLOCKED_REQUIRES_MANUAL"
    #: The attempt failed for a technical reason and may be retried.
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SubmissionRequest:
    """The listing to submit, provider-neutrally."""

    target_url: str
    submission_url: str | None
    title: str | None
    description: str | None
    anchor_text: str | None
    category: str | None = None
    contact_email: str | None = None
    extra_fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubmissionOutcome:
    """The result of an attempt."""

    status: SubmissionOutcomeStatus
    submitted_url: str | None = None
    #: Why a human is needed, or why it failed. A failure class, never a raw
    #: HTTP body.
    reason: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def needs_human(self) -> bool:
        return self.status is SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL


@runtime_checkable
class SubmissionProvider(Protocol):
    """Performs or records a listing submission."""

    method: str

    async def submit(self, request: SubmissionRequest) -> SubmissionOutcome:
        """Attempt the submission.

        Returning ``BLOCKED_REQUIRES_MANUAL`` is always permitted and is the
        required response whenever proceeding would mean circumventing a
        publisher's controls.
        """
        ...

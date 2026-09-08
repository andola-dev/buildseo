"""The submission state machine.

A declarative transition table rather than conditionals scattered through the
service. Three reasons that matters here:

* The legal moves are reviewable in one place, which is what a workflow with a
  human approval gate needs.
* ``GET /submissions/state-machine`` can publish the table, so a client renders
  exactly the actions the backend will accept.
* An illegal move is a single ``InvalidStateTransitionError`` (409) instead of
  a subtly wrong state written by a code path nobody checked.

The gate itself is ``PENDING_APPROVAL -> SUBMITTED``. Nothing reaches a
publisher without a person holding ``submission.approve`` having authorised
that specific submission, and the database enforces the same rule through
``ck_submissions_submitted_requires_approval``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.core.enums import SubmissionStatus
from app.core.exceptions import InvalidStateTransitionError

S = SubmissionStatus

#: Legal transitions. A status absent from a value set cannot be reached from
#: that key, whatever the caller asks for.
TRANSITIONS: Mapping[SubmissionStatus, frozenset[SubmissionStatus]] = MappingProxyType(
    {
        # Prepared but not yet worked on.
        S.READY: frozenset({S.IN_PROGRESS, S.REJECTED, S.FAILED}),
        # Content is being drafted/edited.
        S.IN_PROGRESS: frozenset({S.PENDING_APPROVAL, S.REJECTED, S.FAILED}),
        # Waiting on a human. Back to IN_PROGRESS when changes are requested.
        S.PENDING_APPROVAL: frozenset({S.SUBMITTED, S.IN_PROGRESS, S.REJECTED}),
        # Sent to the publisher; awaiting their decision.
        S.SUBMITTED: frozenset({S.VERIFICATION_PENDING, S.PUBLISHED, S.FAILED}),
        S.VERIFICATION_PENDING: frozenset({S.PUBLISHED, S.FAILED}),
        # Live; verification confirms the link is actually present.
        S.PUBLISHED: frozenset({S.VERIFIED, S.VERIFICATION_PENDING, S.FAILED}),
        # A failed attempt can be retried from the start.
        S.FAILED: frozenset({S.READY}),
        # Terminal.
        S.VERIFIED: frozenset(),
        S.REJECTED: frozenset(),
    }
)

#: Statuses that cannot be left (except FAILED, which allows a retry).
TERMINAL_STATUSES: frozenset[SubmissionStatus] = frozenset({S.VERIFIED, S.REJECTED})

#: Reaching any of these requires a recorded approval. Mirrors the database
#: CHECK constraint so the rule holds even for a direct SQL update.
APPROVAL_REQUIRED_STATUSES: frozenset[SubmissionStatus] = frozenset(
    {S.SUBMITTED, S.PUBLISHED, S.VERIFICATION_PENDING, S.VERIFIED}
)

#: The status a newly prepared submission starts in.
INITIAL_STATUS: SubmissionStatus = S.READY


def allowed_targets(current: SubmissionStatus | str) -> frozenset[SubmissionStatus]:
    """Statuses reachable from ``current``."""
    return TRANSITIONS.get(SubmissionStatus(current), frozenset())


def can_transition(current: SubmissionStatus | str, target: SubmissionStatus | str) -> bool:
    return SubmissionStatus(target) in allowed_targets(current)


def assert_transition(current: SubmissionStatus | str, target: SubmissionStatus | str) -> None:
    """Raise unless the move is legal.

    Raises:
        InvalidStateTransitionError: mapped to HTTP 409.
    """
    if not can_transition(current, target):
        raise InvalidStateTransitionError.between(
            "submission", str(SubmissionStatus(current).value), str(SubmissionStatus(target).value)
        )


def requires_approval(target: SubmissionStatus | str) -> bool:
    """Whether reaching ``target`` needs a recorded human approval."""
    return SubmissionStatus(target) in APPROVAL_REQUIRED_STATUSES


def is_terminal(status: SubmissionStatus | str) -> bool:
    return SubmissionStatus(status) in TERMINAL_STATUSES


def describe() -> dict[str, object]:
    """Serialisable description for ``GET /submissions/state-machine``."""
    return {
        "statuses": [status.value for status in SubmissionStatus],
        "transitions": {
            status.value: sorted(target.value for target in targets)
            for status, targets in TRANSITIONS.items()
        },
        "terminal_statuses": sorted(status.value for status in TERMINAL_STATUSES),
        "approval_required_for": sorted(status.value for status in APPROVAL_REQUIRED_STATUSES),
    }

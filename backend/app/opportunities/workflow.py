"""The opportunity state machine.

Same pattern as the submission workflow: one declarative table, so the
lifecycle is reviewable and an illegal move is a 409 rather than a corrupt
row.

The path a listing takes is: discovered → qualified → selected for a campaign
→ ready to submit → submitted → published. ``REJECTED`` and ``EXPIRED`` are
dead ends, and only ``FAILED`` can be retried.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.core.enums import OpportunityStatus
from app.core.exceptions import InvalidStateTransitionError

O = OpportunityStatus  # noqa: E741 - reads naturally in the table below

TRANSITIONS: Mapping[OpportunityStatus, frozenset[OpportunityStatus]] = MappingProxyType(
    {
        O.DISCOVERED: frozenset({O.QUALIFYING, O.REJECTED}),
        O.QUALIFYING: frozenset({O.QUALIFIED, O.REJECTED}),
        O.QUALIFIED: frozenset({O.SELECTED, O.REJECTED, O.EXPIRED}),
        O.SELECTED: frozenset({O.READY, O.QUALIFIED, O.REJECTED}),
        O.READY: frozenset({O.SUBMITTED, O.REJECTED, O.EXPIRED}),
        O.SUBMITTED: frozenset({O.PUBLISHED, O.FAILED}),
        O.FAILED: frozenset({O.READY, O.REJECTED}),
        # Terminal.
        O.PUBLISHED: frozenset(),
        O.REJECTED: frozenset(),
        O.EXPIRED: frozenset(),
    }
)

TERMINAL_STATUSES: frozenset[OpportunityStatus] = frozenset({O.PUBLISHED, O.REJECTED, O.EXPIRED})

#: Statuses from which a submission may be prepared.
SUBMITTABLE_STATUSES: frozenset[OpportunityStatus] = frozenset({O.SELECTED, O.READY})

INITIAL_STATUS: OpportunityStatus = O.DISCOVERED


def allowed_targets(current: OpportunityStatus | str) -> frozenset[OpportunityStatus]:
    return TRANSITIONS.get(OpportunityStatus(current), frozenset())


def can_transition(current: OpportunityStatus | str, target: OpportunityStatus | str) -> bool:
    return OpportunityStatus(target) in allowed_targets(current)


def assert_transition(current: OpportunityStatus | str, target: OpportunityStatus | str) -> None:
    """Raise unless the move is legal."""
    if not can_transition(current, target):
        raise InvalidStateTransitionError.between(
            "opportunity",
            str(OpportunityStatus(current).value),
            str(OpportunityStatus(target).value),
        )


def is_terminal(status: OpportunityStatus | str) -> bool:
    return OpportunityStatus(status) in TERMINAL_STATUSES


def is_submittable(status: OpportunityStatus | str) -> bool:
    """Whether a submission may be prepared from this status."""
    return OpportunityStatus(status) in SUBMITTABLE_STATUSES


def describe() -> dict[str, object]:
    return {
        "statuses": [status.value for status in OpportunityStatus],
        "transitions": {
            status.value: sorted(target.value for target in targets)
            for status, targets in TRANSITIONS.items()
        },
        "terminal_statuses": sorted(status.value for status in TERMINAL_STATUSES),
        "submittable_statuses": sorted(status.value for status in SUBMITTABLE_STATUSES),
    }

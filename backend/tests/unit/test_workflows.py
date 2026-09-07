"""Opportunity and submission state machines.

The declarative transition tables are the only place a lifecycle is defined,
so these tests are what guarantee the approval gate cannot be skipped and no
status is unreachable or inescapable by accident.
"""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

import app.opportunities.workflow as opportunity_workflow
import app.submissions.workflow as submission_workflow
from app.core.enums import OpportunityStatus as O
from app.core.enums import SubmissionStatus as S
from app.core.exceptions import InvalidStateTransitionError

pytestmark = pytest.mark.unit

WORKFLOWS = [
    pytest.param(submission_workflow, S, id="submission"),
    pytest.param(opportunity_workflow, O, id="opportunity"),
]


def _reachable(table, start) -> set:
    seen, stack = {start}, [start]
    while stack:
        for target in table[stack.pop()]:
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


class TestTableIntegrity:
    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_every_status_is_a_key(self, workflow, enum) -> None:
        # A status missing from the table would be a silent dead end.
        assert set(workflow.TRANSITIONS) == set(enum)

    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_no_transition_points_at_an_unknown_status(self, workflow, enum) -> None:
        for source, targets in workflow.TRANSITIONS.items():
            assert targets <= set(enum), source

    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_no_self_transitions(self, workflow, enum) -> None:
        for source, targets in workflow.TRANSITIONS.items():
            assert source not in targets

    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_every_status_is_reachable_from_the_initial_one(self, workflow, enum) -> None:
        # An unreachable status is either dead code or a missing edge.
        unreachable = set(enum) - _reachable(workflow.TRANSITIONS, workflow.INITIAL_STATUS)
        assert not unreachable, f"unreachable: {sorted(s.value for s in unreachable)}"

    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_terminal_statuses_have_no_way_out(self, workflow, enum) -> None:
        for status in workflow.TERMINAL_STATUSES:
            assert workflow.allowed_targets(status) == frozenset()
            assert workflow.is_terminal(status)
            for other in enum:
                assert not workflow.can_transition(status, other)

    @pytest.mark.parametrize(("workflow", "enum"), WORKFLOWS)
    def test_description_is_json_serialisable(self, workflow, enum) -> None:
        described = workflow.describe()
        assert json.dumps(described)
        assert len(described["statuses"]) == len(list(enum))


class TestSubmissionApprovalGate:
    """PENDING_APPROVAL -> SUBMITTED is the human-in-the-loop gate."""

    def test_the_gate_is_the_only_route_to_submitted(self) -> None:
        assert submission_workflow.can_transition(S.PENDING_APPROVAL, S.SUBMITTED)
        for source in S:
            if source is S.PENDING_APPROVAL:
                continue
            assert not submission_workflow.can_transition(source, S.SUBMITTED), source

    @pytest.mark.parametrize("source", [S.READY, S.IN_PROGRESS])
    def test_review_cannot_be_skipped(self, source: S) -> None:
        assert not submission_workflow.can_transition(source, S.SUBMITTED)
        assert not submission_workflow.can_transition(source, S.PUBLISHED)

    def test_changes_requested_returns_a_submission_to_the_author(self) -> None:
        assert submission_workflow.can_transition(S.PENDING_APPROVAL, S.IN_PROGRESS)

    @pytest.mark.parametrize(
        "status", [S.SUBMITTED, S.PUBLISHED, S.VERIFICATION_PENDING, S.VERIFIED]
    )
    def test_post_approval_statuses_require_an_approval(self, status: S) -> None:
        assert submission_workflow.requires_approval(status)

    @pytest.mark.parametrize("status", [S.READY, S.IN_PROGRESS, S.PENDING_APPROVAL])
    def test_pre_approval_statuses_do_not(self, status: S) -> None:
        assert not submission_workflow.requires_approval(status)


class TestSubmissionLifecycle:
    def test_the_happy_path_end_to_end(self) -> None:
        path = [
            S.READY,
            S.IN_PROGRESS,
            S.PENDING_APPROVAL,
            S.SUBMITTED,
            S.PUBLISHED,
            S.VERIFIED,
        ]
        for current, target in pairwise(path):
            submission_workflow.assert_transition(current, target)

    def test_the_awaiting_verification_branch(self) -> None:
        submission_workflow.assert_transition(S.SUBMITTED, S.VERIFICATION_PENDING)
        submission_workflow.assert_transition(S.VERIFICATION_PENDING, S.PUBLISHED)

    def test_a_failed_submission_can_be_retried(self) -> None:
        submission_workflow.assert_transition(S.SUBMITTED, S.FAILED)
        submission_workflow.assert_transition(S.FAILED, S.READY)
        assert not submission_workflow.is_terminal(S.FAILED)

    def test_an_illegal_move_raises_a_conflict_with_context(self) -> None:
        with pytest.raises(InvalidStateTransitionError) as excinfo:
            submission_workflow.assert_transition(S.VERIFIED, S.READY)
        assert excinfo.value.status_code == 409
        assert excinfo.value.details == {
            "entity": "submission",
            "from": "VERIFIED",
            "to": "READY",
        }

    def test_accepts_plain_strings_from_the_database(self) -> None:
        assert submission_workflow.can_transition("PENDING_APPROVAL", "SUBMITTED")


class TestOpportunityLifecycle:
    def test_the_happy_path_end_to_end(self) -> None:
        path = [
            O.DISCOVERED,
            O.QUALIFYING,
            O.QUALIFIED,
            O.SELECTED,
            O.READY,
            O.SUBMITTED,
            O.PUBLISHED,
        ]
        for current, target in pairwise(path):
            opportunity_workflow.assert_transition(current, target)

    def test_qualification_cannot_be_skipped(self) -> None:
        assert not opportunity_workflow.can_transition(O.DISCOVERED, O.QUALIFIED)
        assert not opportunity_workflow.can_transition(O.DISCOVERED, O.SUBMITTED)

    def test_an_opportunity_must_be_selected_before_it_is_ready(self) -> None:
        assert not opportunity_workflow.can_transition(O.QUALIFIED, O.READY)

    def test_a_selection_can_be_undone(self) -> None:
        assert opportunity_workflow.can_transition(O.SELECTED, O.QUALIFIED)

    @pytest.mark.parametrize("status", [O.SELECTED, O.READY])
    def test_only_selected_or_ready_may_be_submitted(self, status: O) -> None:
        assert opportunity_workflow.is_submittable(status)

    @pytest.mark.parametrize(
        "status",
        [O.DISCOVERED, O.QUALIFYING, O.QUALIFIED, O.PUBLISHED, O.REJECTED, O.EXPIRED],
    )
    def test_other_statuses_may_not_be_submitted(self, status: O) -> None:
        assert not opportunity_workflow.is_submittable(status)

    def test_error_names_the_entity(self) -> None:
        with pytest.raises(InvalidStateTransitionError) as excinfo:
            opportunity_workflow.assert_transition(O.PUBLISHED, O.READY)
        assert excinfo.value.details["entity"] == "opportunity"

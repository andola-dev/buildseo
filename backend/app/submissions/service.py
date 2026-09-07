"""Submission workflow.

Where the platform's central business rules are enforced in application code:

* **Only FREE publishers.** Checked when a submission is created and again
  before it is executed. The database enforces it independently through
  ``trg_submissions_free_only``, so the rule survives a bug here.
* **A human approves.** Nothing reaches ``SUBMITTED`` without an approval
  record naming the person who authorised it. The state machine forbids the
  shortcut and a CHECK constraint forbids the row.
* **Publisher controls are respected.** When a submission provider reports
  ``BLOCKED_REQUIRES_MANUAL`` — a CAPTCHA, an anti-bot challenge, a login, a
  ToS restriction — the submission is routed to a person, never forced through.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.enums import (
    OpportunityStatus,
    PricingType,
    SubmissionMethod,
    SubmissionStatus,
)
from app.core.exceptions import (
    BusinessRuleError,
    PaidPlacementNotAllowedError,
    ResourceNotFoundError,
    SubmissionError,
)
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.integrations.submission.base import (
    SubmissionOutcomeStatus,
    SubmissionProvider,
    SubmissionRequest,
)
from app.models.opportunities import Opportunity
from app.models.publishers import Publisher
from app.models.submissions import Submission
from app.opportunities import workflow as opportunity_workflow
from app.repositories.opportunities import OpportunityRepository
from app.repositories.submissions import GeneratedContentRepository, SubmissionRepository
from app.schemas.submissions import (
    SubmissionApproveRequest,
    SubmissionCreate,
    SubmissionExecuteRequest,
    SubmissionUpdate,
    SubmissionVerifyRequest,
)
from app.submissions import workflow
from app.submissions.verification import LinkVerifier

logger = get_logger(__name__)


class SubmissionService:
    """Prepares, approves, executes and verifies submissions."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        submissions: SubmissionRepository,
        opportunities: OpportunityRepository,
        contents: GeneratedContentRepository,
        audit: AuditService,
        manual_provider: SubmissionProvider,
        form_provider: SubmissionProvider | None = None,
        verifier: LinkVerifier | None = None,
    ) -> None:
        self._session = session
        self._submissions = submissions
        self._opportunities = opportunities
        self._contents = contents
        self._audit = audit
        self._manual = manual_provider
        self._form = form_provider
        self._verifier = verifier

    # -------------------------------------------------------------- create --

    async def create(self, payload: SubmissionCreate) -> Submission:
        """Prepare a submission. Sends nothing."""
        opportunity, publisher = await self._load(payload.opportunity_id)
        await self._assert_free(publisher, opportunity)

        if not opportunity_workflow.is_submittable(opportunity.status):
            raise BusinessRuleError(
                "An opportunity must be SELECTED or READY before a submission "
                f"can be prepared (it is {opportunity.status})",
                code="OPPORTUNITY_NOT_SUBMITTABLE",
                details={"status": opportunity.status},
            )

        live = await self._submissions.get_live_for_opportunity(payload.opportunity_id)
        if live is not None:
            # Matches the partial unique index; pre-checked so the caller gets
            # an explanation and the existing id rather than a constraint error.
            raise BusinessRuleError(
                "This opportunity already has an active submission",
                code="SUBMISSION_ALREADY_ACTIVE",
                details={"submission_id": str(live.id), "status": live.status},
            )

        title, description, anchor = await self._resolve_content(payload, opportunity)
        method = payload.submission_method or _default_method(publisher)

        submission = self._submissions.new(
            campaign_id=opportunity.campaign_id,
            opportunity_id=opportunity.id,
            status=workflow.INITIAL_STATUS.value,
            target_url=opportunity.target_url,
            submitted_url=opportunity.submission_url or publisher.submission_url,
            anchor_text=anchor,
            submitted_title=title,
            submitted_description=description,
            submission_method=method.value,
            notes=payload.notes,
        )
        await self._submissions.flush()

        await self._audit.record(
            AuditAction.SUBMISSION_CREATED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={
                "campaign_id": str(submission.campaign_id),
                "opportunity_id": str(submission.opportunity_id),
                "submission_method": submission.submission_method,
                "target_url": submission.target_url,
            },
        )
        return submission

    async def _resolve_content(
        self, payload: SubmissionCreate, opportunity: Opportunity
    ) -> tuple[str | None, str | None, str | None]:
        """Choose the copy to submit.

        Prefers the *approved* AI draft, which is the point of the review gate:
        what a person signed off is what gets sent.
        """
        if payload.use_approved_content:
            approved = await self._contents.get_approved_for_opportunity(opportunity.id)
            if approved is not None:
                fields = approved.generated_content or {}
                return (
                    payload.submitted_title or fields.get("listing_title") or None,
                    payload.submitted_description
                    or fields.get("long_description")
                    or fields.get("short_description")
                    or None,
                    payload.anchor_text or fields.get("anchor_suggestion") or None,
                )
        return (
            payload.submitted_title or opportunity.suggested_title,
            payload.submitted_description or opportunity.suggested_description,
            payload.anchor_text or opportunity.suggested_anchor,
        )

    async def _load(self, opportunity_id: UUID) -> tuple[Opportunity, Publisher]:
        pair = await self._opportunities.get_with_publisher(opportunity_id)
        if pair is None:
            raise ResourceNotFoundError.for_resource("opportunity", opportunity_id)
        return pair

    async def _assert_free(self, publisher: Publisher, opportunity: Opportunity) -> None:
        """Rules 1 and 2. Refusals are audited, not just rejected."""
        if publisher.pricing_type == PricingType.FREE.value:
            return
        await self._audit.record(
            AuditAction.PAID_PLACEMENT_BLOCKED,
            resource_type="publisher",
            resource_id=publisher.id,
            metadata={
                "publisher_id": str(publisher.id),
                "normalized_domain": publisher.normalized_domain,
                "pricing_type": publisher.pricing_type,
                "opportunity_id": str(opportunity.id),
            },
        )
        raise PaidPlacementNotAllowedError(
            details={
                "publisher_id": str(publisher.id),
                "normalized_domain": publisher.normalized_domain,
                "pricing_type": publisher.pricing_type,
            }
        )

    # ----------------------------------------------------------- retrieval --

    async def get(self, submission_id: UUID) -> Submission:
        return await self._submissions.get_or_raise(submission_id, resource="submission")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        status: str | None = None,
        campaign_id: UUID | None = None,
        opportunity_id: UUID | None = None,
        submission_method: str | None = None,
        search: str | None = None,
    ) -> Page[Submission]:
        filters = self._submissions.build_filters(
            status=status,
            campaign_id=campaign_id,
            opportunity_id=opportunity_id,
            submission_method=submission_method,
            search=search,
        )
        return await self._submissions.list_page(page=page, sort=sort, filters=filters)

    async def review_queue(self, *, limit: int = 50) -> list[Submission]:
        return await self._submissions.list_awaiting_approval(limit=limit)

    # -------------------------------------------------------------- update --

    async def update(self, submission_id: UUID, payload: SubmissionUpdate) -> Submission:
        """Edit the payload of a submission that has not been sent."""
        submission = await self.get(submission_id)
        if submission.status not in (
            SubmissionStatus.READY.value,
            SubmissionStatus.IN_PROGRESS.value,
            SubmissionStatus.PENDING_APPROVAL.value,
        ):
            raise SubmissionError(
                f"A submission in {submission.status} can no longer be edited",
                code="SUBMISSION_NOT_EDITABLE",
                details={"status": submission.status},
            )

        changed: list[str] = []
        for field in ("anchor_text", "submitted_title", "submitted_description", "notes"):
            value = getattr(payload, field)
            if value is not None and value != getattr(submission, field):
                setattr(submission, field, value)
                changed.append(field)
        if (
            payload.submission_method is not None
            and payload.submission_method.value != submission.submission_method
        ):
            submission.submission_method = payload.submission_method.value
            changed.append("submission_method")

        # Editing content after approval would defeat the review, so an edit
        # sends the submission back for re-review.
        if changed and submission.status == SubmissionStatus.PENDING_APPROVAL.value:
            submission.status = SubmissionStatus.IN_PROGRESS.value
            submission.approved_by_user_id = None
            submission.approved_at = None
            changed.append("status")

        await self._submissions.flush()
        await self._audit.record(
            AuditAction.SUBMISSION_UPDATED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={"changed_fields": changed, "status": submission.status},
        )
        return submission

    # --------------------------------------------------------- transitions --

    async def transition(
        self, submission_id: UUID, *, target: SubmissionStatus, reason: str | None = None
    ) -> Submission:
        """Move a submission, validating against the state machine.

        Reaching an approval-gated status through this route still requires an
        existing approval record, so it is not a way around the gate.
        """
        submission = await self.get(submission_id)
        workflow.assert_transition(submission.status, target)

        if workflow.requires_approval(target) and submission.approved_by_user_id is None:
            raise SubmissionError(
                f"{target.value} requires an approval. Call POST "
                "/submissions/{id}/approve first.",
                code="APPROVAL_REQUIRED",
                details={"target_status": target.value},
            )

        submission.status = target.value
        if target is SubmissionStatus.FAILED and reason:
            submission.failure_reason = reason[:500]
        await self._submissions.flush()

        await self._audit.record(
            AuditAction.SUBMISSION_UPDATED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={"status": target.value, "reason": reason},
        )
        return submission

    async def prepare_for_review(self, submission_id: UUID) -> Submission:
        """Move a submission into the human review queue."""
        submission = await self.get(submission_id)
        if submission.status == SubmissionStatus.READY.value:
            workflow.assert_transition(submission.status, SubmissionStatus.IN_PROGRESS)
            submission.status = SubmissionStatus.IN_PROGRESS.value
        workflow.assert_transition(submission.status, SubmissionStatus.PENDING_APPROVAL)

        if not submission.submitted_title:
            # Nothing for a reviewer to look at.
            raise BusinessRuleError(
                "A submission needs a title before it can be reviewed. Generate "
                "content or set one explicitly.",
                code="SUBMISSION_CONTENT_MISSING",
            )

        submission.status = SubmissionStatus.PENDING_APPROVAL.value
        await self._submissions.flush()
        await self._audit.record(
            AuditAction.SUBMISSION_UPDATED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={"status": submission.status},
        )
        return submission

    async def approve(
        self, submission_id: UUID, *, approver_id: UUID, payload: SubmissionApproveRequest
    ) -> Submission:
        """Record the human approval that unlocks sending.

        The caller must hold ``submission.approve``, which the SEO Specialist
        role deliberately lacks: preparing work and authorising it are separate
        duties.
        """
        submission = await self.get(submission_id)
        if submission.status != SubmissionStatus.PENDING_APPROVAL.value:
            raise SubmissionError(
                "Only a submission awaiting approval can be approved "
                f"(it is {submission.status})",
                code="SUBMISSION_NOT_AWAITING_APPROVAL",
                details={"status": submission.status},
            )

        submission.approved_by_user_id = approver_id
        submission.approved_at = datetime.now(UTC)
        if payload.notes:
            submission.notes = payload.notes
        await self._submissions.flush()

        await self._audit.record(
            AuditAction.SUBMISSION_APPROVED,
            resource_type="submission",
            resource_id=submission.id,
            user_id=approver_id,
            metadata={
                "opportunity_id": str(submission.opportunity_id),
                "approved_by_user_id": str(approver_id),
            },
        )
        logger.info(
            "submission approved",
            extra={"submission_id": str(submission.id), "approver_id": str(approver_id)},
        )
        return submission

    # ------------------------------------------------------------- execute --

    async def execute(
        self, submission_id: UUID, *, payload: SubmissionExecuteRequest
    ) -> Submission:
        """Perform or record the submission.

        Requires an approval already on the row. Re-checks the FREE-only rule,
        because a publisher's pricing could have been corrected between
        approval and execution.
        """
        submission = await self.get(submission_id)
        if submission.approved_by_user_id is None:
            raise SubmissionError(
                "This submission has not been approved",
                code="APPROVAL_REQUIRED",
                details={"status": submission.status},
            )
        workflow.assert_transition(submission.status, SubmissionStatus.SUBMITTED)

        opportunity, publisher = await self._load(submission.opportunity_id)
        await self._assert_free(publisher, opportunity)

        provider = self._provider_for(submission.submission_method)
        outcome = await provider.submit(
            SubmissionRequest(
                target_url=submission.target_url,
                submission_url=payload.submitted_url or submission.submitted_url,
                title=submission.submitted_title,
                description=submission.submitted_description,
                anchor_text=submission.anchor_text,
                category=opportunity.category,
            )
        )

        if outcome.needs_human:
            # The provider declined because proceeding would mean working
            # around the publisher's controls. Fall back to manual, keep the
            # approval, and record why.
            submission.submission_method = SubmissionMethod.MANUAL.value
            submission.status = SubmissionStatus.SUBMITTED.value
            submission.submitted_at = datetime.now(UTC)
            submission.submitted_url = outcome.submitted_url or submission.submitted_url
            submission.notes = _append_note(submission.notes, f"manual required: {outcome.reason}")
            submission.verification_evidence = {
                **submission.verification_evidence,
                "submission_preflight": outcome.evidence,
                "manual_reason": outcome.reason,
            }
            await self._submissions.flush()
            await self._audit.record(
                AuditAction.SUBMISSION_EXECUTED,
                resource_type="submission",
                resource_id=submission.id,
                metadata={
                    "opportunity_id": str(submission.opportunity_id),
                    "submitted_url": submission.submitted_url,
                    "submission_method": submission.submission_method,
                    "status": submission.status,
                    "reason": outcome.reason,
                },
            )
            await self._advance_opportunity(opportunity, OpportunityStatus.SUBMITTED)
            return submission

        if outcome.status is SubmissionOutcomeStatus.FAILED:
            submission.status = SubmissionStatus.FAILED.value
            submission.failure_reason = (outcome.reason or "submission_failed")[:500]
            await self._submissions.flush()
            await self._audit.record(
                AuditAction.SUBMISSION_FAILED,
                resource_type="submission",
                resource_id=submission.id,
                metadata={
                    "opportunity_id": str(submission.opportunity_id),
                    "failure_reason": submission.failure_reason,
                },
            )
            await self._advance_opportunity(opportunity, OpportunityStatus.FAILED)
            return submission

        submission.status = SubmissionStatus.SUBMITTED.value
        submission.submitted_at = datetime.now(UTC)
        submission.submitted_url = outcome.submitted_url or submission.submitted_url
        if payload.notes:
            submission.notes = _append_note(submission.notes, payload.notes)

        if payload.mark_published or outcome.status is SubmissionOutcomeStatus.PUBLISHED:
            workflow.assert_transition(submission.status, SubmissionStatus.PUBLISHED)
            submission.status = SubmissionStatus.PUBLISHED.value
            submission.published_at = datetime.now(UTC)
        else:
            workflow.assert_transition(submission.status, SubmissionStatus.VERIFICATION_PENDING)
            submission.status = SubmissionStatus.VERIFICATION_PENDING.value

        await self._submissions.flush()
        await self._audit.record(
            AuditAction.SUBMISSION_EXECUTED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={
                "opportunity_id": str(submission.opportunity_id),
                "submitted_url": submission.submitted_url,
                "submission_method": submission.submission_method,
                "status": submission.status,
            },
        )
        await self._advance_opportunity(
            opportunity,
            (
                OpportunityStatus.PUBLISHED
                if submission.status == SubmissionStatus.PUBLISHED.value
                else OpportunityStatus.SUBMITTED
            ),
        )
        return submission

    def _provider_for(self, method: str) -> SubmissionProvider:
        """Pick the adapter for a submission method, defaulting to manual."""
        if method == SubmissionMethod.FORM.value and self._form is not None:
            return self._form
        return self._manual

    async def _advance_opportunity(
        self, opportunity: Opportunity, target: OpportunityStatus
    ) -> None:
        """Keep the opportunity's status in step, without failing the submission.

        A legal-but-unexpected opportunity state must not roll back a
        submission that actually happened, so an illegal move is logged rather
        than raised.
        """
        if opportunity_workflow.can_transition(opportunity.status, target):
            opportunity.status = target.value
            await self._opportunities.flush()
            return
        logger.info(
            "opportunity status left unchanged: transition not permitted",
            extra={
                "opportunity_id": str(opportunity.id),
                "from": opportunity.status,
                "to": target.value,
            },
        )

    # -------------------------------------------------------------- verify --

    async def verify(self, submission_id: UUID, *, payload: SubmissionVerifyRequest) -> Submission:
        """Confirm the published listing really carries the link."""
        submission = await self.get(submission_id)
        if submission.status not in (
            SubmissionStatus.SUBMITTED.value,
            SubmissionStatus.VERIFICATION_PENDING.value,
            SubmissionStatus.PUBLISHED.value,
        ):
            raise SubmissionError(
                f"A submission in {submission.status} cannot be verified",
                code="SUBMISSION_NOT_VERIFIABLE",
                details={"status": submission.status},
            )

        published_url = payload.published_url or submission.submitted_url
        if payload.fetch_live and self._verifier is not None:
            if not published_url:
                raise BusinessRuleError(
                    "No published URL is recorded for this submission. Supply "
                    "published_url, or record the outcome manually.",
                    code="PUBLISHED_URL_REQUIRED",
                )
            result = await self._verifier.verify(
                published_url=published_url, target_url=submission.target_url
            )
            verified = result.verified
            evidence: dict[str, object] = {
                "checked_url": result.checked_url,
                "http_status": result.http_status,
                "page_reachable": result.page_reachable,
                "found_href": result.found_href,
                "anchor_text": result.anchor_text,
                "rel": result.rel,
                "is_dofollow": result.is_dofollow,
                "error": result.error,
                "verified_at": datetime.now(UTC).isoformat(),
                **result.evidence,
            }
        else:
            if payload.manual_result is None:
                raise BusinessRuleError(
                    "Set manual_result when fetch_live is false",
                    code="MANUAL_RESULT_REQUIRED",
                )
            verified = payload.manual_result
            evidence = {
                "manual": True,
                "checked_url": published_url,
                "verified_at": datetime.now(UTC).isoformat(),
            }

        submission.verification_evidence = {
            **submission.verification_evidence,
            "verification": evidence,
        }

        if verified:
            if submission.status != SubmissionStatus.PUBLISHED.value:
                workflow.assert_transition(submission.status, SubmissionStatus.PUBLISHED)
                submission.status = SubmissionStatus.PUBLISHED.value
                submission.published_at = submission.published_at or datetime.now(UTC)
            workflow.assert_transition(submission.status, SubmissionStatus.VERIFIED)
            submission.status = SubmissionStatus.VERIFIED.value
            submission.verified_at = datetime.now(UTC)
        else:
            # Not found is not necessarily permanent — a directory may still be
            # moderating — so the submission stays awaiting verification rather
            # than failing, unless the page itself is gone.
            if submission.status == SubmissionStatus.SUBMITTED.value:
                submission.status = SubmissionStatus.VERIFICATION_PENDING.value
            submission.failure_reason = (
                f"link not verified: {evidence.get('error') or 'not found'}"
            )[:500]

        await self._submissions.flush()
        await self._audit.record(
            AuditAction.SUBMISSION_VERIFIED,
            resource_type="submission",
            resource_id=submission.id,
            metadata={
                "opportunity_id": str(submission.opportunity_id),
                "verified": verified,
                "published_url": published_url,
            },
        )
        return submission

    async def delete(self, submission_id: UUID) -> None:
        submission = await self.get(submission_id)
        opportunity_id = submission.opportunity_id
        await self._submissions.delete(submission)
        await self._submissions.flush()
        await self._audit.record(
            AuditAction.SUBMISSION_DELETED,
            resource_type="submission",
            resource_id=submission_id,
            metadata={"opportunity_id": str(opportunity_id)},
        )


def _default_method(publisher: Publisher) -> SubmissionMethod:
    """Use the publisher's recorded method, defaulting to manual.

    An UNKNOWN method means manual: guessing that a directory can be automated
    is exactly the assumption that leads to circumventing its controls.
    """
    try:
        method = SubmissionMethod(publisher.submission_method)
    except ValueError:  # pragma: no cover - constrained by a CHECK
        return SubmissionMethod.MANUAL
    return SubmissionMethod.MANUAL if method is SubmissionMethod.UNKNOWN else method


def _append_note(existing: str | None, addition: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    line = f"[{stamp}] {addition}"
    return f"{existing}\n{line}" if existing else line

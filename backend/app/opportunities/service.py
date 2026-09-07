"""Opportunity lifecycle management."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.enums import OpportunityStatus, OpportunityType, PricingType, PublisherStatus
from app.core.exceptions import (
    BusinessRuleError,
    PaidPlacementNotAllowedError,
    ResourceNotFoundError,
)
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.opportunities import Opportunity
from app.models.publishers import Publisher
from app.opportunities import workflow
from app.repositories.campaigns import CampaignRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.publishers import PublisherRepository
from app.schemas.opportunities import OpportunityCreate, OpportunityUpdate

logger = get_logger(__name__)

#: Publisher category -> the opportunity type it produces, so a caller does
#: not have to restate what a directory is.
_CATEGORY_TO_TYPE: dict[str, OpportunityType] = {
    "BUSINESS_DIRECTORY": OpportunityType.FREE_DIRECTORY_LISTING,
    "LOCAL_DIRECTORY": OpportunityType.FREE_LOCAL_LISTING,
    "COMPANY_LISTING": OpportunityType.FREE_COMPANY_PROFILE,
    "STARTUP_DIRECTORY": OpportunityType.FREE_STARTUP_LISTING,
    "SOFTWARE_DIRECTORY": OpportunityType.FREE_SOFTWARE_LISTING,
    "INDUSTRY_DIRECTORY": OpportunityType.FREE_INDUSTRY_LISTING,
    "ORGANIZATION_LISTING": OpportunityType.FREE_ORGANIZATION_LISTING,
    "PROFILE_LISTING": OpportunityType.FREE_PROFILE_LISTING,
}


class OpportunityService:
    """Creates opportunities and moves them through their lifecycle."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        opportunities: OpportunityRepository,
        publishers: PublisherRepository,
        campaigns: CampaignRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._opportunities = opportunities
        self._publishers = publishers
        self._campaigns = campaigns
        self._audit = audit

    # -------------------------------------------------------------- create --

    async def create(self, payload: OpportunityCreate) -> tuple[Opportunity, bool]:
        """Create an opportunity. Returns ``(opportunity, created)``.

        Idempotent: repeating the call with the same campaign, publisher and
        target URL returns the existing row with ``created=False`` rather than
        a 409, so a client that retried after a timeout gets the right answer.
        """
        campaign = await self._campaigns.get(payload.campaign_id)
        if campaign is None:
            raise ResourceNotFoundError.for_resource("campaign", payload.campaign_id)
        publisher = await self._publishers.get(payload.publisher_id)
        if publisher is None:
            raise ResourceNotFoundError.for_resource("publisher", payload.publisher_id)

        self._assert_free(publisher)

        existing = await self._opportunities.find_duplicate(
            campaign_id=payload.campaign_id,
            publisher_id=payload.publisher_id,
            target_url=payload.target_url,
        )
        if existing is not None:
            return existing, False

        opportunity = self._opportunities.new(
            campaign_id=payload.campaign_id,
            publisher_id=payload.publisher_id,
            opportunity_type=self._resolve_type(payload, publisher).value,
            target_url=payload.target_url,
            suggested_anchor=payload.suggested_anchor,
            suggested_title=payload.suggested_title,
            suggested_description=payload.suggested_description,
            category=payload.category.value if payload.category else publisher.category,
            status=OpportunityStatus.DISCOVERED.value,
            priority=payload.priority,
            # Snapshot: a later publisher edit must not silently retarget
            # work that is already queued.
            submission_url=publisher.submission_url,
            discovered_at=datetime.now(UTC),
        )
        await self._opportunities.flush()
        await self._audit.record(
            AuditAction.OPPORTUNITY_CREATED,
            resource_type="opportunity",
            resource_id=opportunity.id,
            metadata={
                "campaign_id": str(payload.campaign_id),
                "publisher_id": str(payload.publisher_id),
                "opportunity_type": opportunity.opportunity_type,
                "target_url": opportunity.target_url,
            },
        )
        return opportunity, True

    @staticmethod
    def _resolve_type(payload: OpportunityCreate, publisher: Publisher) -> OpportunityType:
        """Use the caller's type, or infer it from the publisher's category."""
        if payload.opportunity_type is not OpportunityType.FREE_DIRECTORY_LISTING:
            return payload.opportunity_type
        if publisher.category:
            return _CATEGORY_TO_TYPE.get(publisher.category, payload.opportunity_type)
        return payload.opportunity_type

    def _assert_free(self, publisher: Publisher) -> None:
        """MVP rules 1 and 2: only FREE publishers may enter the workflow.

        Checked when the opportunity is created rather than only at submission
        time, so a paid publisher never reaches a work queue in the first
        place. The submission path checks again, and the database enforces it
        a third time.
        """
        if publisher.pricing_type != PricingType.FREE.value:
            raise PaidPlacementNotAllowedError(
                details={
                    "publisher_id": str(publisher.id),
                    "normalized_domain": publisher.normalized_domain,
                    "pricing_type": publisher.pricing_type,
                },
            )

    # ----------------------------------------------------------- retrieval --

    async def get(self, opportunity_id: UUID) -> Opportunity:
        return await self._opportunities.get_or_raise(opportunity_id, resource="opportunity")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        status: str | None = None,
        campaign_id: UUID | None = None,
        publisher_id: UUID | None = None,
        opportunity_type: str | None = None,
        category: str | None = None,
        min_priority: int | None = None,
        min_score: float | None = None,
        search: str | None = None,
    ) -> Page[Opportunity]:
        filters = self._opportunities.build_filters(
            status=status,
            campaign_id=campaign_id,
            publisher_id=publisher_id,
            opportunity_type=opportunity_type,
            category=category,
            min_priority=min_priority,
            min_score=min_score,
            search=search,
        )
        return await self._opportunities.list_page(page=page, sort=sort, filters=filters)

    async def workqueue(self, *, campaign_id: UUID, limit: int = 50) -> list[Opportunity]:
        return await self._opportunities.list_workqueue(campaign_id=campaign_id, limit=limit)

    # -------------------------------------------------------------- update --

    async def update(self, opportunity_id: UUID, payload: OpportunityUpdate) -> Opportunity:
        opportunity = await self.get(opportunity_id)
        changed: list[str] = []
        for field in ("suggested_anchor", "suggested_title", "suggested_description", "priority"):
            value = getattr(payload, field)
            if value is not None and value != getattr(opportunity, field):
                setattr(opportunity, field, value)
                changed.append(field)
        if payload.category is not None and payload.category.value != opportunity.category:
            opportunity.category = payload.category.value
            changed.append("category")

        await self._opportunities.flush()
        await self._audit.record(
            AuditAction.OPPORTUNITY_UPDATED,
            resource_type="opportunity",
            resource_id=opportunity.id,
            metadata={"changed_fields": changed, "priority": opportunity.priority},
        )
        return opportunity

    # --------------------------------------------------------- transitions --

    async def transition(
        self,
        opportunity_id: UUID,
        *,
        target: OpportunityStatus,
        reason: str | None = None,
    ) -> Opportunity:
        """Move an opportunity, validating the move against the state machine."""
        opportunity = await self.get(opportunity_id)
        workflow.assert_transition(opportunity.status, target)

        if target is OpportunityStatus.REJECTED and not reason:
            raise BusinessRuleError(
                "A reason is required when rejecting an opportunity",
                code="REJECTION_REASON_REQUIRED",
            )

        opportunity.status = target.value
        if target is OpportunityStatus.QUALIFIED:
            opportunity.qualified_at = datetime.now(UTC)
        if target is OpportunityStatus.REJECTED:
            opportunity.rejection_reason = reason

        await self._opportunities.flush()
        await self._audit.record(
            _TRANSITION_ACTIONS.get(target, AuditAction.OPPORTUNITY_UPDATED),
            resource_type="opportunity",
            resource_id=opportunity.id,
            metadata={
                "campaign_id": str(opportunity.campaign_id),
                "publisher_id": str(opportunity.publisher_id),
                "priority": opportunity.priority,
                "qualification_score": opportunity.qualification_score,
                "reason": reason,
            },
        )
        return opportunity

    async def qualify(self, opportunity_id: UUID) -> Opportunity:
        """Score an opportunity from its publisher's qualification.

        The opportunity inherits the publisher's judgement rather than
        re-crawling: a publisher's quality is a property of the site, so
        scoring it once per publisher instead of once per opportunity avoids
        hundreds of duplicate fetches for a campaign.
        """
        pair = await self._opportunities.get_with_publisher(opportunity_id)
        if pair is None:
            raise ResourceNotFoundError.for_resource("opportunity", opportunity_id)
        opportunity, publisher = pair

        if opportunity.status == OpportunityStatus.DISCOVERED.value:
            workflow.assert_transition(opportunity.status, OpportunityStatus.QUALIFYING)
            opportunity.status = OpportunityStatus.QUALIFYING.value

        score = _combined_score(publisher)
        opportunity.qualification_score = score
        # Priority tracks the score by default but remains hand-editable.
        opportunity.priority = max(0, min(100, round(score)))
        opportunity.submission_url = publisher.submission_url or opportunity.submission_url

        eligible = (
            publisher.pricing_type == PricingType.FREE.value
            and publisher.status == PublisherStatus.QUALIFIED.value
        )
        opportunity.status = (
            OpportunityStatus.QUALIFIED.value if eligible else OpportunityStatus.REJECTED.value
        )
        if not eligible:
            opportunity.rejection_reason = (
                "publisher is not a qualified free listing site "
                f"(pricing={publisher.pricing_type}, status={publisher.status})"
            )[:255]
        else:
            opportunity.qualified_at = datetime.now(UTC)

        await self._opportunities.flush()
        await self._audit.record(
            AuditAction.OPPORTUNITY_QUALIFIED,
            resource_type="opportunity",
            resource_id=opportunity.id,
            metadata={
                "qualification_score": score,
                "priority": opportunity.priority,
                "reason": opportunity.rejection_reason,
            },
        )
        return opportunity

    async def delete(self, opportunity_id: UUID) -> None:
        opportunity = await self.get(opportunity_id)
        campaign_id, publisher_id = opportunity.campaign_id, opportunity.publisher_id
        await self._opportunities.delete(opportunity)
        await self._opportunities.flush()
        await self._audit.record(
            AuditAction.OPPORTUNITY_DELETED,
            resource_type="opportunity",
            resource_id=opportunity_id,
            metadata={"campaign_id": str(campaign_id), "publisher_id": str(publisher_id)},
        )


_TRANSITION_ACTIONS: dict[OpportunityStatus, AuditAction] = {
    OpportunityStatus.QUALIFIED: AuditAction.OPPORTUNITY_QUALIFIED,
    OpportunityStatus.SELECTED: AuditAction.OPPORTUNITY_SELECTED,
    OpportunityStatus.REJECTED: AuditAction.OPPORTUNITY_REJECTED,
}


def _combined_score(publisher: Publisher) -> float:
    """Derive an opportunity score from the publisher's stored scores.

    Prefers the opportunity score the qualification service already computed
    (weights included); falls back to a plain quality-minus-spam blend when a
    publisher predates scoring.
    """
    stored = (publisher.signals or {}).get("opportunity_score")
    if isinstance(stored, (int, float)):
        return round(float(stored), 2)
    quality = float(publisher.quality_score or 0)
    spam = float(publisher.spam_score or 0)
    return round(max(0.0, min(100.0, quality - spam * 0.5)), 2)

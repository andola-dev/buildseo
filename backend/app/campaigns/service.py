"""Campaign management."""

from __future__ import annotations

from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.core.enums import OpportunityStatus, SubmissionStatus
from app.core.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.campaigns import Campaign
from app.models.opportunities import Opportunity
from app.models.submissions import Submission
from app.repositories.campaigns import CampaignRepository
from app.repositories.client_websites import ClientWebsiteRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.submissions import SubmissionRepository
from app.schemas.campaigns import CampaignCreate, CampaignStats, CampaignUpdate


class CampaignService:
    """CRUD and progress reporting for campaigns."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        campaigns: CampaignRepository,
        client_websites: ClientWebsiteRepository,
        opportunities: OpportunityRepository,
        submissions: SubmissionRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._campaigns = campaigns
        self._client_websites = client_websites
        self._opportunities = opportunities
        self._submissions = submissions
        self._audit = audit

    async def create(self, payload: CampaignCreate) -> Campaign:
        # Confirms the client website belongs to this tenant. The repository is
        # tenant-scoped, so a website from another workspace reads as absent.
        website = await self._client_websites.get(payload.client_website_id)
        if website is None:
            raise ResourceNotFoundError.for_resource("client_website", payload.client_website_id)

        if await self._campaigns.get_by_name(
            client_website_id=payload.client_website_id, name=payload.name
        ):
            raise DuplicateResourceError(
                f"A campaign named '{payload.name}' already exists for this client website",
                code="CAMPAIGN_NAME_TAKEN",
            )

        campaign = self._campaigns.new(
            client_website_id=payload.client_website_id,
            name=payload.name,
            description=payload.description,
            status=payload.status.value,
            # Inherit the client's market when the campaign does not override it.
            target_country=payload.target_country or website.target_country,
            target_language=payload.target_language or website.target_language,
            budget=payload.budget,
            # Not taken from the request: this platform builds free listings
            # only, and the column is pinned true by a database CHECK.
            free_only=True,
            target_link_count=payload.target_link_count,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        await self._campaigns.flush()
        await self._audit.record(
            AuditAction.CAMPAIGN_CREATED,
            resource_type="campaign",
            resource_id=campaign.id,
            metadata={
                "name": campaign.name,
                "client_website_id": str(campaign.client_website_id),
                "status": campaign.status,
            },
        )
        return campaign

    async def get(self, campaign_id: UUID) -> Campaign:
        return await self._campaigns.get_or_raise(campaign_id, resource="campaign")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        status: str | None = None,
        client_website_id: UUID | None = None,
        target_country: str | None = None,
        search: str | None = None,
    ) -> Page[Campaign]:
        filters = self._campaigns.build_filters(
            status=status,
            client_website_id=client_website_id,
            target_country=target_country,
            search=search,
        )
        return await self._campaigns.list_page(page=page, sort=sort, filters=filters)

    async def update(self, campaign_id: UUID, payload: CampaignUpdate) -> Campaign:
        campaign = await self.get(campaign_id)
        changed: list[str] = []
        for field in (
            "name",
            "description",
            "target_country",
            "target_language",
            "budget",
            "target_link_count",
            "start_date",
            "end_date",
        ):
            value = getattr(payload, field)
            if value is not None and value != getattr(campaign, field):
                setattr(campaign, field, value)
                changed.append(field)
        if payload.status is not None and payload.status.value != campaign.status:
            campaign.status = payload.status.value
            changed.append("status")

        await self._campaigns.flush()
        await self._audit.record(
            AuditAction.CAMPAIGN_UPDATED,
            resource_type="campaign",
            resource_id=campaign.id,
            metadata={"changed_fields": changed, "status": campaign.status},
        )
        return campaign

    async def delete(self, campaign_id: UUID) -> None:
        campaign = await self.get(campaign_id)
        name = campaign.name
        await self._campaigns.delete(campaign)
        await self._campaigns.flush()
        await self._audit.record(
            AuditAction.CAMPAIGN_DELETED,
            resource_type="campaign",
            resource_id=campaign_id,
            metadata={"name": name},
        )

    async def stats(self, campaign_id: UUID) -> CampaignStats:
        """Progress counters.

        Counted in the database rather than by loading rows: a campaign can
        hold six figures of opportunities.
        """
        campaign = await self.get(campaign_id)
        base = [Opportunity.campaign_id == campaign_id]
        submission_base = [Submission.campaign_id == campaign_id]

        return CampaignStats(
            campaign_id=campaign.id,
            opportunities_total=await self._opportunities.count(base),
            opportunities_qualified=await self._opportunities.count(
                [*base, Opportunity.status == OpportunityStatus.QUALIFIED.value]
            ),
            opportunities_ready=await self._opportunities.count(
                [*base, Opportunity.status == OpportunityStatus.READY.value]
            ),
            submissions_total=await self._submissions.count(submission_base),
            submissions_published=await self._submissions.count(
                [*submission_base, Submission.status == SubmissionStatus.PUBLISHED.value]
            ),
            submissions_verified=await self._submissions.count(
                [*submission_base, Submission.status == SubmissionStatus.VERIFIED.value]
            ),
            target_link_count=campaign.target_link_count,
        )

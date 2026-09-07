"""Opportunity data access."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import OpportunityStatus
from app.models.opportunities import Opportunity
from app.models.publishers import Publisher
from app.repositories.base import TenantRepository


class OpportunityRepository(TenantRepository[Opportunity]):
    model = Opportunity
    sortable_fields = frozenset(
        {
            "created_at",
            "updated_at",
            "status",
            "priority",
            "qualification_score",
            "discovered_at",
            "qualified_at",
        }
    )
    default_sort = "created_at"

    async def find_duplicate(
        self, *, campaign_id: UUID, publisher_id: UUID, target_url: str
    ) -> Opportunity | None:
        """The idempotency lookup, matching the unique constraint exactly.

        Checking here turns a retried create into a 200 with the existing row
        rather than a 409 from the database.
        """
        result = await self.session.execute(
            self._select().where(
                Opportunity.campaign_id == campaign_id,
                Opportunity.publisher_id == publisher_id,
                Opportunity.target_url == target_url,
            )
        )
        return result.scalar_one_or_none()

    async def get_with_publisher(
        self, opportunity_id: UUID
    ) -> tuple[Opportunity, Publisher] | None:
        """Load an opportunity with its publisher in one round trip.

        The submission path needs the publisher's ``pricing_type`` to enforce
        the FREE-only rule, and this avoids the N+1 that a lazy relationship
        would cause (models use ``lazy="raise"`` precisely to make that
        impossible to do by accident).
        """
        result = await self.session.execute(
            select(Opportunity, Publisher)
            .join(Publisher, Publisher.id == Opportunity.publisher_id)
            .where(
                Opportunity.tenant_id == self.tenant_id,
                Opportunity.id == opportunity_id,
            )
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def list_workqueue(self, *, campaign_id: UUID, limit: int = 50) -> list[Opportunity]:
        """Highest-priority actionable opportunities for a campaign.

        Backed by the partial index ``ix_opportunities_tenant_id_workqueue``.
        """
        result = await self.session.execute(
            self._select()
            .where(
                Opportunity.campaign_id == campaign_id,
                Opportunity.status.in_(
                    [
                        OpportunityStatus.QUALIFIED.value,
                        OpportunityStatus.SELECTED.value,
                        OpportunityStatus.READY.value,
                    ]
                ),
            )
            .order_by(Opportunity.priority.desc(), Opportunity.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def build_filters(
        self,
        *,
        status: str | None = None,
        campaign_id: UUID | None = None,
        publisher_id: UUID | None = None,
        opportunity_type: str | None = None,
        category: str | None = None,
        min_priority: int | None = None,
        min_score: float | None = None,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Opportunity.status == status)
        if campaign_id:
            filters.append(Opportunity.campaign_id == campaign_id)
        if publisher_id:
            filters.append(Opportunity.publisher_id == publisher_id)
        if opportunity_type:
            filters.append(Opportunity.opportunity_type == opportunity_type)
        if category:
            filters.append(Opportunity.category == category)
        if min_priority is not None:
            filters.append(Opportunity.priority >= min_priority)
        if min_score is not None:
            filters.append(Opportunity.qualification_score >= min_score)
        if search:
            filters.append(Opportunity.target_url.ilike(f"%{search.strip()}%"))
        return filters

"""Campaign data access."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.sql.elements import ColumnElement

from app.models.campaigns import Campaign
from app.repositories.base import TenantRepository


class CampaignRepository(TenantRepository[Campaign]):
    model = Campaign
    sortable_fields = frozenset(
        {"created_at", "updated_at", "name", "status", "start_date", "end_date"}
    )
    default_sort = "created_at"

    async def get_by_name(self, *, client_website_id: UUID, name: str) -> Campaign | None:
        result = await self.session.execute(
            self._select().where(
                Campaign.client_website_id == client_website_id, Campaign.name == name
            )
        )
        return result.scalar_one_or_none()

    def build_filters(
        self,
        *,
        status: str | None = None,
        client_website_id: UUID | None = None,
        target_country: str | None = None,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Campaign.status == status)
        if client_website_id:
            filters.append(Campaign.client_website_id == client_website_id)
        if target_country:
            filters.append(Campaign.target_country == target_country)
        if search:
            filters.append(Campaign.name.ilike(f"%{search.strip()}%"))
        return filters

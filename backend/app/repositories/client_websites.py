"""Client website data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.client_websites import ClientWebsite
from app.repositories.base import TenantRepository


class ClientWebsiteRepository(TenantRepository[ClientWebsite]):
    model = ClientWebsite
    sortable_fields = frozenset({"created_at", "updated_at", "name", "normalized_domain", "status"})
    default_sort = "created_at"

    async def get_by_normalized_domain(self, normalized_domain: str) -> ClientWebsite | None:
        """Duplicate detection against the canonical domain form."""
        result = await self.session.execute(
            self._select().where(ClientWebsite.normalized_domain == normalized_domain)
        )
        return result.scalar_one_or_none()

    def build_filters(
        self,
        *,
        status: str | None = None,
        industry: str | None = None,
        target_country: str | None = None,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(ClientWebsite.status == status)
        if industry:
            filters.append(ClientWebsite.industry == industry)
        if target_country:
            filters.append(ClientWebsite.target_country == target_country)
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    ClientWebsite.name.ilike(term),
                    ClientWebsite.normalized_domain.ilike(term),
                )
            )
        return filters

    async def domains_in_use(self, normalized_domains: Sequence[str]) -> set[str]:
        if not normalized_domains:
            return set()
        result = await self.session.execute(
            self._select().where(ClientWebsite.normalized_domain.in_(list(normalized_domains)))
        )
        return {row.normalized_domain for row in result.scalars().all()}

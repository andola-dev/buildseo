"""Publisher and discovery-run data access."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import PricingType, PublisherStatus
from app.models.publishers import DiscoveryRun, Publisher
from app.repositories.base import TenantRepository


class PublisherRepository(TenantRepository[Publisher]):
    model = Publisher
    sortable_fields = frozenset(
        {
            "created_at",
            "updated_at",
            "domain",
            "normalized_domain",
            "name",
            "status",
            "quality_score",
            "relevance_score",
            "spam_score",
            "authority_score",
            "organic_traffic",
            "last_checked_at",
        }
    )
    default_sort = "created_at"

    async def get_by_normalized_domain(self, normalized_domain: str) -> Publisher | None:
        """The de-duplication lookup.

        Callers normalise first, so ``www.example.com`` and
        ``https://example.com/`` both find the same row.
        """
        result = await self.session.execute(
            self._select().where(Publisher.normalized_domain == normalized_domain)
        )
        return result.scalar_one_or_none()

    async def existing_domains(self, normalized_domains: Sequence[str]) -> set[str]:
        """Bulk duplicate check, so discovery does one query instead of N."""
        if not normalized_domains:
            return set()
        result = await self.session.execute(
            select(Publisher.normalized_domain).where(
                Publisher.tenant_id == self.tenant_id,
                Publisher.normalized_domain.in_(list(normalized_domains)),
            )
        )
        return set(result.scalars().all())

    async def list_submittable(self, *, limit: int = 100) -> list[Publisher]:
        """Free, qualified publishers — the only ones eligible for submission.

        Backed by the partial index ``ix_publishers_tenant_id_free_qualified``.
        """
        result = await self.session.execute(
            self._select()
            .where(
                Publisher.pricing_type == PricingType.FREE.value,
                Publisher.status == PublisherStatus.QUALIFIED.value,
            )
            .order_by(Publisher.quality_score.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())

    def build_filters(
        self,
        *,
        status: str | None = None,
        pricing_type: str | None = None,
        category: str | None = None,
        country: str | None = None,
        language: str | None = None,
        submission_method: str | None = None,
        min_quality_score: float | None = None,
        max_spam_score: float | None = None,
        free_only: bool = False,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Publisher.status == status)
        if pricing_type:
            filters.append(Publisher.pricing_type == pricing_type)
        if free_only:
            filters.append(Publisher.pricing_type == PricingType.FREE.value)
        if category:
            filters.append(Publisher.category == category)
        if country:
            filters.append(Publisher.country == country)
        if language:
            filters.append(Publisher.language == language)
        if submission_method:
            filters.append(Publisher.submission_method == submission_method)
        if min_quality_score is not None:
            filters.append(Publisher.quality_score >= min_quality_score)
        if max_spam_score is not None:
            filters.append(Publisher.spam_score <= max_spam_score)
        if search:
            term = f"%{search.strip()}%"
            # Served by the trigram indexes created in revision 0018.
            filters.append(
                or_(
                    Publisher.name.ilike(term),
                    Publisher.normalized_domain.ilike(term),
                )
            )
        return filters


class DiscoveryRunRepository(TenantRepository[DiscoveryRun]):
    model = DiscoveryRun
    sortable_fields = frozenset({"created_at", "updated_at", "status", "provider"})
    default_sort = "created_at"

    def build_filters(
        self,
        *,
        status: str | None = None,
        provider: str | None = None,
        campaign_id: UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(DiscoveryRun.status == status)
        if provider:
            filters.append(DiscoveryRun.provider == provider)
        if campaign_id:
            filters.append(DiscoveryRun.campaign_id == campaign_id)
        return filters

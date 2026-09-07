"""Publisher CRUD."""

from __future__ import annotations

from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.core.domains import normalize_domain, normalize_url
from app.core.enums import PricingType
from app.core.exceptions import DuplicateResourceError
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.publishers import Publisher
from app.repositories.publishers import PublisherRepository
from app.schemas.publishers import PublisherCreate, PublisherUpdate


class PublisherService:
    """Manages publisher candidates.

    De-duplication is by canonical domain, computed here rather than trusted
    from the client, so ``https://www.Example.com/`` and ``example.com`` can
    never become two rows.
    """

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        publishers: PublisherRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._publishers = publishers
        self._audit = audit

    async def create(self, payload: PublisherCreate) -> Publisher:
        website_url = normalize_url(payload.website_url)
        normalized = normalize_domain(website_url)

        existing = await self._publishers.get_by_normalized_domain(normalized)
        if existing is not None:
            raise DuplicateResourceError(
                f"A publisher for '{normalized}' already exists in this workspace",
                code="PUBLISHER_EXISTS",
                details={"normalized_domain": normalized, "existing_id": str(existing.id)},
            )

        publisher = self._publishers.new(
            domain=normalized,
            normalized_domain=normalized,
            website_url=website_url,
            name=payload.name,
            description=payload.description,
            category=payload.category.value if payload.category else None,
            country=payload.country,
            language=payload.language,
            submission_url=payload.submission_url,
            contact_url=payload.contact_url,
            submission_method=payload.submission_method.value,
            pricing_type=payload.pricing_type.value,
            link_type=payload.link_type.value,
            dofollow_supported=payload.dofollow_supported,
            nofollow_supported=payload.nofollow_supported,
            status=payload.status.value,
        )
        await self._publishers.flush()
        await self._audit.record(
            AuditAction.PUBLISHER_CREATED,
            resource_type="publisher",
            resource_id=publisher.id,
            metadata={
                "normalized_domain": normalized,
                "pricing_type": publisher.pricing_type,
                "category": publisher.category,
                "country": publisher.country,
            },
        )
        return publisher

    async def get(self, publisher_id: UUID) -> Publisher:
        return await self._publishers.get_or_raise(publisher_id, resource="publisher")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
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
    ) -> Page[Publisher]:
        filters = self._publishers.build_filters(
            status=status,
            pricing_type=pricing_type,
            category=category,
            country=country,
            language=language,
            submission_method=submission_method,
            min_quality_score=min_quality_score,
            max_spam_score=max_spam_score,
            free_only=free_only,
            search=search,
        )
        return await self._publishers.list_page(page=page, sort=sort, filters=filters)

    async def update(self, publisher_id: UUID, payload: PublisherUpdate) -> Publisher:
        publisher = await self.get(publisher_id)
        changed: list[str] = []

        for field in (
            "name",
            "description",
            "country",
            "language",
            "submission_url",
            "contact_url",
            "dofollow_supported",
            "nofollow_supported",
        ):
            value = getattr(payload, field)
            if value is not None and value != getattr(publisher, field):
                setattr(publisher, field, value)
                changed.append(field)

        for field in ("category", "submission_method", "pricing_type", "link_type", "status"):
            enum_value = getattr(payload, field)
            if enum_value is not None and enum_value.value != getattr(publisher, field):
                setattr(publisher, field, enum_value.value)
                changed.append(field)

        await self._publishers.flush()
        await self._audit.record(
            AuditAction.PUBLISHER_UPDATED,
            resource_type="publisher",
            resource_id=publisher.id,
            metadata={
                "changed_fields": changed,
                "pricing_type": publisher.pricing_type,
                "status": publisher.status,
                "normalized_domain": publisher.normalized_domain,
            },
        )
        return publisher

    async def delete(self, publisher_id: UUID) -> None:
        publisher = await self.get(publisher_id)
        normalized = publisher.normalized_domain
        await self._publishers.delete(publisher)
        await self._publishers.flush()
        await self._audit.record(
            AuditAction.PUBLISHER_DELETED,
            resource_type="publisher",
            resource_id=publisher_id,
            metadata={"normalized_domain": normalized},
        )

    async def list_submittable(self, *, limit: int = 100) -> list[Publisher]:
        """FREE, QUALIFIED publishers — the only ones eligible for submission."""
        return await self._publishers.list_submittable(limit=limit)

    @staticmethod
    def is_submittable(publisher: Publisher) -> bool:
        """MVP rule 1: only FREE publishers may enter the workflow."""
        return publisher.pricing_type == PricingType.FREE.value

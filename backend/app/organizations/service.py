"""Client website management."""

from __future__ import annotations

from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.core.domains import normalize_domain, normalize_url
from app.core.exceptions import DuplicateResourceError
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.client_websites import ClientWebsite
from app.repositories.client_websites import ClientWebsiteRepository
from app.schemas.client_websites import ClientWebsiteCreate, ClientWebsiteUpdate


class ClientWebsiteService:
    """CRUD for a tenant's client sites.

    ``domain`` and ``normalized_domain`` are always derived from
    ``website_url`` here rather than accepted from the client, so the stored
    canonical identity cannot contradict the URL it came from.
    """

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        repository: ClientWebsiteRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._repository = repository
        self._audit = audit

    async def create(self, payload: ClientWebsiteCreate) -> ClientWebsite:
        website_url = normalize_url(payload.website_url)
        normalized = normalize_domain(website_url)

        existing = await self._repository.get_by_normalized_domain(normalized)
        if existing is not None:
            # Pre-checked so the caller gets a specific message rather than a
            # bare constraint violation from the database.
            raise DuplicateResourceError(
                f"A client website for '{normalized}' already exists",
                code="CLIENT_WEBSITE_EXISTS",
                details={"normalized_domain": normalized, "existing_id": str(existing.id)},
            )

        website = self._repository.new(
            name=payload.name,
            domain=normalized,
            normalized_domain=normalized,
            website_url=website_url,
            description=payload.description,
            industry=payload.industry,
            target_country=payload.target_country,
            target_countries=list(dict.fromkeys(payload.target_countries)),
            target_language=payload.target_language,
            status=payload.status.value,
        )
        await self._repository.flush()
        await self._audit.record(
            AuditAction.CLIENT_WEBSITE_CREATED,
            resource_type="client_website",
            resource_id=website.id,
            metadata={"name": website.name, "normalized_domain": normalized},
        )
        return website

    async def get(self, website_id: UUID) -> ClientWebsite:
        return await self._repository.get_or_raise(website_id, resource="client_website")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        status: str | None = None,
        industry: str | None = None,
        target_country: str | None = None,
        search: str | None = None,
    ) -> Page[ClientWebsite]:
        filters = self._repository.build_filters(
            status=status, industry=industry, target_country=target_country, search=search
        )
        return await self._repository.list_page(page=page, sort=sort, filters=filters)

    async def update(self, website_id: UUID, payload: ClientWebsiteUpdate) -> ClientWebsite:
        website = await self.get(website_id)
        changed: list[str] = []

        for field in ("name", "description", "industry", "target_country", "target_language"):
            value = getattr(payload, field)
            if value is not None and value != getattr(website, field):
                setattr(website, field, value)
                changed.append(field)
        if payload.target_countries is not None:
            website.target_countries = list(dict.fromkeys(payload.target_countries))
            changed.append("target_countries")
        if payload.status is not None and payload.status.value != website.status:
            website.status = payload.status.value
            changed.append("status")

        await self._repository.flush()
        await self._audit.record(
            AuditAction.CLIENT_WEBSITE_UPDATED,
            resource_type="client_website",
            resource_id=website.id,
            metadata={"changed_fields": changed, "status": website.status},
        )
        return website

    async def delete(self, website_id: UUID) -> None:
        """Delete a client website.

        Campaigns (and therefore their opportunities and submissions) cascade,
        which is why this needs its own permission.
        """
        website = await self.get(website_id)
        name, normalized = website.name, website.normalized_domain
        await self._repository.delete(website)
        await self._repository.flush()
        await self._audit.record(
            AuditAction.CLIENT_WEBSITE_DELETED,
            resource_type="client_website",
            resource_id=website_id,
            metadata={"name": name, "normalized_domain": normalized},
        )

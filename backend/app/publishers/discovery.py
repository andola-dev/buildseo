"""Publisher discovery orchestration.

Runs a discovery provider, normalises every candidate, de-duplicates against
what the workspace already has, and records the run.

The de-duplication is the part that matters operationally: discovery is meant
to be re-run, so the same directory must not accumulate rows. Candidates are
canonicalised first and then checked against existing domains in a single
query, so a 200-result run costs one lookup rather than 200.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.domains import normalize_domain, normalize_url
from app.core.enums import DiscoveryRunStatus, PricingType, PublisherStatus
from app.core.exceptions import ProviderError, ValidationError
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.integrations.discovery.base import (
    DiscoveredPublisher,
    DiscoveryQuery,
    PublisherDiscoveryProvider,
)
from app.models.publishers import DiscoveryRun
from app.repositories.publishers import DiscoveryRunRepository, PublisherRepository

logger = get_logger(__name__)


class DiscoveryService:
    """Executes a discovery run and materialises new publishers."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        publishers: PublisherRepository,
        runs: DiscoveryRunRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._publishers = publishers
        self._runs = runs
        self._audit = audit

    async def start_run(
        self, *, provider_key: str, query: DiscoveryQuery, campaign_id: UUID | None
    ) -> DiscoveryRun:
        """Create the run record before any provider call.

        Recorded first so a provider that hangs or crashes still leaves an
        auditable row rather than nothing.
        """
        run = self._runs.new(
            campaign_id=campaign_id,
            provider=provider_key,
            query=query.as_dict(),
            status=DiscoveryRunStatus.PENDING.value,
        )
        await self._runs.flush()
        await self._audit.record(
            AuditAction.PUBLISHER_DISCOVERY_STARTED,
            resource_type="discovery_run",
            resource_id=run.id,
            metadata={
                "provider": provider_key,
                "keywords": list(query.keywords),
                "country": query.country,
                "category": query.category.value if query.category else None,
                "limit": query.limit,
                "campaign_id": str(campaign_id) if campaign_id else None,
            },
        )
        return run

    async def execute(
        self,
        run: DiscoveryRun,
        *,
        provider: PublisherDiscoveryProvider,
        query: DiscoveryQuery,
    ) -> DiscoveryRun:
        """Run the provider and persist the results."""
        run.status = DiscoveryRunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        await self._runs.flush()

        try:
            candidates = await provider.search(query)
        except ProviderError as exc:
            run.status = DiscoveryRunStatus.FAILED.value
            # The error *class*, never the provider's body: it can echo a key.
            run.error = exc.code
            run.finished_at = datetime.now(UTC)
            await self._runs.flush()
            logger.warning(
                "discovery run failed",
                extra={"run_id": str(run.id), "provider": run.provider, "error_code": exc.code},
            )
            await self._record_completion(run)
            return run

        created, duplicates = await self._materialise(candidates, run)

        run.results_found = len(candidates)
        run.publishers_created = created
        run.duplicates_skipped = duplicates
        run.status = DiscoveryRunStatus.COMPLETED.value
        run.finished_at = datetime.now(UTC)
        await self._runs.flush()

        logger.info(
            "discovery run completed",
            extra={
                "run_id": str(run.id),
                "provider": run.provider,
                "results_found": len(candidates),
                "publishers_created": created,
                "duplicates_skipped": duplicates,
            },
        )
        await self._record_completion(run)
        return run

    async def _materialise(
        self, candidates: list[DiscoveredPublisher], run: DiscoveryRun
    ) -> tuple[int, int]:
        """Insert the new candidates, skipping ones already known."""
        normalised: list[tuple[str, str, DiscoveredPublisher]] = []
        for candidate in candidates:
            try:
                website_url = normalize_url(candidate.website_url)
                domain = normalize_domain(website_url)
            except ValidationError:
                # A provider returned something that is not a usable public
                # domain (a hallucinated host, an IP, a malformed URL).
                logger.debug("discovery candidate rejected as not a valid domain")
                continue
            normalised.append((domain, website_url, candidate))

        # One query for the whole batch instead of one per candidate.
        existing = await self._publishers.existing_domains([domain for domain, _, _ in normalised])

        created = 0
        duplicates = 0
        seen_in_batch: set[str] = set()
        for domain, website_url, candidate in normalised:
            if domain in existing or domain in seen_in_batch:
                duplicates += 1
                continue
            seen_in_batch.add(domain)

            self._publishers.new(
                domain=domain,
                normalized_domain=domain,
                website_url=website_url,
                name=candidate.name,
                description=candidate.description,
                category=candidate.category.value if candidate.category else None,
                country=candidate.country,
                language=candidate.language,
                submission_url=candidate.submission_url,
                contact_url=candidate.contact_url,
                submission_method=candidate.submission_method.value,
                # Discovery never asserts pricing. A candidate stays UNKNOWN —
                # and therefore un-submittable — until qualification confirms a
                # free submission path.
                pricing_type=PricingType.UNKNOWN.value,
                status=PublisherStatus.DISCOVERED.value,
                signals={"discovery": candidate.source_metadata},
                discovery_run_id=run.id,
            )
            created += 1

        await self._publishers.flush()
        return created, duplicates

    async def _record_completion(self, run: DiscoveryRun) -> None:
        await self._audit.record(
            AuditAction.PUBLISHER_DISCOVERY_COMPLETED,
            resource_type="discovery_run",
            resource_id=run.id,
            metadata={
                "provider": run.provider,
                "results_found": run.results_found,
                "publishers_created": run.publishers_created,
                "duplicates_skipped": run.duplicates_skipped,
                "status": run.status,
            },
        )

    async def get_run(self, run_id: UUID) -> DiscoveryRun:
        return await self._runs.get_or_raise(run_id, resource="discovery_run")

    async def list_runs(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        status: str | None = None,
        provider: str | None = None,
        campaign_id: UUID | None = None,
    ) -> Page[DiscoveryRun]:
        filters = self._runs.build_filters(
            status=status, provider=provider, campaign_id=campaign_id
        )
        return await self._runs.list_page(page=page, sort=sort, filters=filters)

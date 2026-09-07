"""Repository behaviour against a real database.

The theme of this module is that a tenant-owned repository takes its scope
from the session, not from its caller. Every read is pre-filtered, every insert
is stamped, and a repository on a session with no validated tenant context
cannot run at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.audit.actions import AuditAction
from app.core.enums import (
    ContentStatus,
    OpportunityStatus,
    OpportunityType,
    PricingType,
    PublisherCategory,
    PublisherStatus,
    SubmissionMethod,
    SubmissionStatus,
)
from app.core.exceptions import ResourceNotFoundError, TenantContextMissingError
from app.core.pagination import PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.publishers import Publisher
from app.repositories.audit import AuditLogRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.publishers import PublisherRepository
from app.repositories.submissions import GeneratedContentRepository, SubmissionRepository
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def session_a(
    session_factory: async_sessionmaker[TenantAwareSession], tenant_a: TenantFixture
) -> AsyncIterator[TenantAwareSession]:
    """A session bound to tenant A, rolled back afterwards."""
    session = session_factory()
    await session.set_tenant_context(tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def unbound_session(
    session_factory: async_sessionmaker[TenantAwareSession],
) -> AsyncIterator[TenantAwareSession]:
    """A session with no tenant context — the failure case we want to prove."""
    session = session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


def _publisher_values(slug: str) -> dict[str, object]:
    return {
        "domain": f"{slug}.test",
        "normalized_domain": f"{slug}.test",
        "website_url": f"https://{slug}.test",
        "name": slug,
        "category": PublisherCategory.BUSINESS_DIRECTORY.value,
        "submission_method": SubmissionMethod.MANUAL.value,
        "pricing_type": PricingType.FREE.value,
        "status": PublisherStatus.QUALIFIED.value,
    }


class TestTenantScoping:
    async def test_repository_takes_tenant_from_session(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        assert repository.tenant_id == tenant_a.tenant_id

    async def test_repository_without_context_refuses_to_query(
        self, unbound_session: TenantAwareSession
    ) -> None:
        """The first line of defence: no context, no query — not an empty result."""
        repository = PublisherRepository(unbound_session)
        with pytest.raises(TenantContextMissingError):
            await repository.get(uuid4())

    async def test_new_ignores_caller_supplied_tenant_id(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture, tenant_b: TenantFixture
    ) -> None:
        """A caller cannot smuggle in another tenant's id, even by accident."""
        repository = PublisherRepository(session_a)
        publisher = repository.new(
            tenant_id=tenant_b.tenant_id,  # type: ignore[arg-type]
            **_publisher_values("smuggled"),
        )
        await repository.flush()
        assert publisher.tenant_id == tenant_a.tenant_id

    async def test_get_returns_none_for_another_tenants_row(
        self, session_a: TenantAwareSession, tenant_b: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        assert await repository.get(tenant_b.free_publisher.id) is None

    async def test_get_or_raise_is_a_404_not_a_403(
        self, session_a: TenantAwareSession, tenant_b: TenantFixture
    ) -> None:
        """404, so an identifier's existence in another tenant is not probeable."""
        repository = PublisherRepository(session_a)
        with pytest.raises(ResourceNotFoundError) as raised:
            await repository.get_or_raise(tenant_b.free_publisher.id, resource="publisher")
        assert raised.value.status_code == 404

    async def test_delete_by_id_will_not_reach_another_tenant(
        self, session_a: TenantAwareSession, tenant_b: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        assert await repository.delete_by_id(tenant_b.free_publisher.id) == 0

    async def test_count_and_exists_are_tenant_scoped(
        self, session_a: TenantAwareSession, tenant_b: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        assert await repository.count() == 2  # the fixture's free + paid publishers
        assert not await repository.exists(
            [Publisher.normalized_domain == tenant_b.free_publisher.normalized_domain]
        )


class TestPagination:
    async def test_pages_are_disjoint_and_cover_every_row(
        self, session_a: TenantAwareSession
    ) -> None:
        """The id tie-breaker is what makes this true for equal sort values."""
        repository = PublisherRepository(session_a)
        for index in range(7):
            repository.new(**_publisher_values(f"page-{index}"))
        await repository.flush()

        seen: list[str] = []
        for number in (1, 2, 3):
            page = await repository.list_page(
                page=PageParams(page=number, page_size=4), sort=SortParams(field="created_at")
            )
            assert page.total == 9
            seen.extend(str(item.id) for item in page.items)

        assert len(seen) == 9
        assert len(set(seen)) == 9

    async def test_total_reflects_the_callers_filters(self, session_a: TenantAwareSession) -> None:
        repository = PublisherRepository(session_a)
        page = await repository.list_page(
            page=PageParams(page=1, page_size=50),
            filters=repository.build_filters(pricing_type=PricingType.PAID.value),
        )
        assert page.total == 1
        assert [publisher.pricing_type for publisher in page.items] == [PricingType.PAID.value]

    async def test_unknown_sort_field_is_rejected(self, session_a: TenantAwareSession) -> None:
        """A 422, rather than silently sorting by something else."""
        repository = PublisherRepository(session_a)
        with pytest.raises(ValueError, match="not a sortable field"):
            await repository.list_page(page=PageParams(), sort=SortParams(field="password_hash"))


class TestPublisherLookups:
    async def test_normalized_domain_lookup_is_the_dedupe_key(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        found = await repository.get_by_normalized_domain(tenant_a.free_publisher.normalized_domain)
        assert found is not None
        assert found.id == tenant_a.free_publisher.id

    async def test_existing_domains_is_a_single_bulk_check(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture, tenant_b: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        existing = await repository.existing_domains(
            [
                tenant_a.free_publisher.normalized_domain,
                tenant_b.free_publisher.normalized_domain,
                "never-seen.test",
            ]
        )
        # Tenant B's domain is *not* reported as existing: discovery for A must
        # be free to add it.
        assert existing == {tenant_a.free_publisher.normalized_domain}

    async def test_existing_domains_short_circuits_on_empty_input(
        self, session_a: TenantAwareSession
    ) -> None:
        repository = PublisherRepository(session_a)
        assert await repository.existing_domains([]) == set()

    async def test_list_submittable_excludes_paid_and_unqualified(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        values = _publisher_values("unqualified-dir")
        values["status"] = PublisherStatus.DISCOVERED.value
        repository.new(**values)
        await repository.flush()

        submittable = await repository.list_submittable()
        assert [publisher.id for publisher in submittable] == [tenant_a.free_publisher.id]

    async def test_search_filter_matches_name_or_domain(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = PublisherRepository(session_a)
        page = await repository.list_page(
            page=PageParams(page=1, page_size=50),
            filters=repository.build_filters(search="freedir"),
        )
        assert [publisher.id for publisher in page.items] == [tenant_a.free_publisher.id]


class TestOpportunityLookups:
    async def test_find_duplicate_matches_the_unique_constraint(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """Checked in Python so a retry is a 200, not a database error."""
        repository = OpportunityRepository(session_a)
        duplicate = await repository.find_duplicate(
            campaign_id=tenant_a.campaign.id,
            publisher_id=tenant_a.free_publisher.id,
            target_url=tenant_a.opportunity.target_url,
        )
        assert duplicate is not None
        assert duplicate.id == tenant_a.opportunity.id

    async def test_find_duplicate_is_exact_not_fuzzy(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = OpportunityRepository(session_a)
        assert (
            await repository.find_duplicate(
                campaign_id=tenant_a.campaign.id,
                publisher_id=tenant_a.free_publisher.id,
                target_url=tenant_a.opportunity.target_url + "pricing",
            )
            is None
        )

    async def test_get_with_publisher_loads_both_in_one_query(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """The submission path needs pricing_type; lazy loading is disabled."""
        repository = OpportunityRepository(session_a)
        loaded = await repository.get_with_publisher(tenant_a.opportunity.id)
        assert loaded is not None
        opportunity, publisher = loaded
        assert opportunity.id == tenant_a.opportunity.id
        assert publisher.pricing_type == PricingType.FREE.value

    async def test_get_with_publisher_refuses_another_tenants_row(
        self, session_a: TenantAwareSession, tenant_b: TenantFixture
    ) -> None:
        repository = OpportunityRepository(session_a)
        assert await repository.get_with_publisher(tenant_b.opportunity.id) is None

    async def test_workqueue_is_ordered_by_priority_then_age(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = OpportunityRepository(session_a)
        low = repository.new(
            campaign_id=tenant_a.campaign.id,
            publisher_id=tenant_a.free_publisher.id,
            opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
            target_url="https://tenant-a-client.test/low",
            status=OpportunityStatus.QUALIFIED.value,
            priority=10,
        )
        high = repository.new(
            campaign_id=tenant_a.campaign.id,
            publisher_id=tenant_a.free_publisher.id,
            opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
            target_url="https://tenant-a-client.test/high",
            status=OpportunityStatus.READY.value,
            priority=95,
        )
        await repository.flush()

        queue = await repository.list_workqueue(campaign_id=tenant_a.campaign.id)
        ids = [opportunity.id for opportunity in queue]
        assert ids[0] == high.id
        assert ids.index(tenant_a.opportunity.id) < ids.index(low.id)

    async def test_workqueue_excludes_non_actionable_states(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = OpportunityRepository(session_a)
        rejected = repository.new(
            campaign_id=tenant_a.campaign.id,
            publisher_id=tenant_a.free_publisher.id,
            opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
            target_url="https://tenant-a-client.test/rejected",
            status=OpportunityStatus.REJECTED.value,
            priority=99,
        )
        await repository.flush()

        queue = await repository.list_workqueue(campaign_id=tenant_a.campaign.id)
        assert rejected.id not in {opportunity.id for opportunity in queue}


class TestSubmissionLookups:
    async def test_live_submission_ignores_terminal_rows(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """A failed attempt must not block a retry."""
        repository = SubmissionRepository(session_a)
        repository.new(
            campaign_id=tenant_a.campaign.id,
            opportunity_id=tenant_a.opportunity.id,
            target_url=tenant_a.opportunity.target_url,
            submission_method=SubmissionMethod.MANUAL.value,
            status=SubmissionStatus.FAILED.value,
        )
        await repository.flush()
        assert await repository.get_live_for_opportunity(tenant_a.opportunity.id) is None

        live = repository.new(
            campaign_id=tenant_a.campaign.id,
            opportunity_id=tenant_a.opportunity.id,
            target_url=tenant_a.opportunity.target_url,
            submission_method=SubmissionMethod.MANUAL.value,
            status=SubmissionStatus.READY.value,
        )
        await repository.flush()

        found = await repository.get_live_for_opportunity(tenant_a.opportunity.id)
        assert found is not None
        assert found.id == live.id

    async def test_review_queue_is_oldest_first(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = SubmissionRepository(session_a)
        awaiting = repository.new(
            campaign_id=tenant_a.campaign.id,
            opportunity_id=tenant_a.opportunity.id,
            target_url=tenant_a.opportunity.target_url,
            submission_method=SubmissionMethod.MANUAL.value,
            status=SubmissionStatus.PENDING_APPROVAL.value,
            submitted_title="Awaiting a human",
        )
        await repository.flush()

        queue = await repository.list_awaiting_approval()
        assert [submission.id for submission in queue] == [awaiting.id]


class TestGeneratedContent:
    async def test_superseding_leaves_history_in_place(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """History is what makes an approval auditable later."""
        repository = GeneratedContentRepository(session_a)
        first = repository.new(
            opportunity_id=tenant_a.opportunity.id,
            content_status=ContentStatus.DRAFT.value,
            generated_content={"listing_title": "First draft"},
        )
        await repository.flush()

        await repository.supersede_drafts(tenant_a.opportunity.id)
        second = repository.new(
            opportunity_id=tenant_a.opportunity.id,
            content_status=ContentStatus.DRAFT.value,
            generated_content={"listing_title": "Second draft"},
        )
        await repository.flush()

        history = await repository.list_for_opportunity(tenant_a.opportunity.id)
        by_id = {content.id: content for content in history}
        assert by_id[first.id].content_status == ContentStatus.SUPERSEDED.value
        assert by_id[second.id].content_status == ContentStatus.DRAFT.value

    async def test_only_an_approved_draft_is_offered_to_a_submission(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        repository = GeneratedContentRepository(session_a)
        repository.new(
            opportunity_id=tenant_a.opportunity.id,
            content_status=ContentStatus.DRAFT.value,
            generated_content={"listing_title": "Unreviewed"},
        )
        await repository.flush()
        assert await repository.get_approved_for_opportunity(tenant_a.opportunity.id) is None

        approved = repository.new(
            opportunity_id=tenant_a.opportunity.id,
            content_status=ContentStatus.APPROVED.value,
            generated_content={"listing_title": "Signed off"},
        )
        await repository.flush()

        found = await repository.get_approved_for_opportunity(tenant_a.opportunity.id)
        assert found is not None
        assert found.id == approved.id


class TestAuditRepositoryIsAppendOnly:
    async def test_the_database_refuses_to_rewrite_history(
        self, session_a: TenantAwareSession, tenant_a: TenantFixture
    ) -> None:
        """Appending works; the audit trail is only readable afterwards.

        The runtime role has UPDATE and DELETE revoked on ``audit_logs`` by
        revision 0018 — proven in ``tests/security`` against that role. Here we
        only assert the repository offers no bespoke mutation helper that would
        invite a future code path to try.
        """
        repository = AuditLogRepository(session_a)
        entry = repository.new(
            user_id=tenant_a.owner.id,
            action=AuditAction.TENANT_CREATED.value,
            resource_type="tenant",
            resource_id=str(tenant_a.tenant_id),
            audit_metadata={"tenant_id": str(tenant_a.tenant_id)},
        )
        await repository.flush()
        assert await repository.get(entry.id) is not None

        for name in ("update", "purge_older_than", "rewrite", "redact"):
            assert not hasattr(AuditLogRepository, name), name

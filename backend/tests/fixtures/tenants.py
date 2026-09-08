"""Two fully-populated workspaces.

Every isolation test needs a second tenant that demonstrably has data, so the
fixtures below build tenant A and tenant B with their own users, roles, client
sites, campaigns, publishers, opportunities and credentials.

Seeding runs as the owner role with the tenant context set for each workspace
in turn — the same handshake the application performs — so the rows are created
exactly as production would create them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bootstrap import AppResources
from app.core.enums import (
    MembershipStatus,
    OpportunityStatus,
    OpportunityType,
    PricingType,
    PublisherCategory,
    PublisherStatus,
    SubmissionMethod,
)
from app.core.security.password import PasswordHasher
from app.db.session import TenantAwareSession
from app.models.campaigns import Campaign
from app.models.client_websites import ClientWebsite
from app.models.opportunities import Opportunity
from app.models.publishers import Publisher
from app.models.tenants import Tenant, TenantMembership
from app.models.users import User
from app.rbac.catalog import PERMISSION_CATALOG
from app.repositories.rbac import PermissionRepository
from app.services.factory import ServiceFactory

PASSWORD = "Fixture!Password123"


@dataclass(slots=True)
class TenantFixture:
    """Everything a test needs to act as one workspace."""

    tenant: Tenant
    owner: User
    owner_membership: TenantMembership
    client_website: ClientWebsite
    campaign: Campaign
    free_publisher: Publisher
    paid_publisher: Publisher
    opportunity: Opportunity

    @property
    def tenant_id(self) -> UUID:
        return self.tenant.id


@pytest_asyncio.fixture
async def seeded_permissions(
    session_factory: async_sessionmaker[TenantAwareSession],
) -> None:
    """Ensure the global permission catalog exists.

    Roles cannot be seeded without it, and it is global rather than
    tenant-owned, so it is inserted once and shared.
    """
    async with session_factory() as session:
        repository = PermissionRepository(session)
        existing = {permission.code for permission in await repository.list_all()}
        from app.models.rbac import Permission

        for spec in PERMISSION_CATALOG:
            if spec.code in existing:
                continue
            session.add(
                Permission(
                    code=spec.code,
                    resource=spec.resource,
                    action=spec.action,
                    description=spec.description,
                )
            )
        await session.commit()


async def _build_tenant(
    *,
    session: TenantAwareSession,
    resources: AppResources,
    slug: str,
    email: str,
    hasher: PasswordHasher,
) -> TenantFixture:
    user = User(
        email=email,
        password_hash=hasher.hash(PASSWORD),
        first_name=slug.title(),
        last_name="Owner",
        is_active=True,
    )
    session.add(user)
    await session.flush()

    services = ServiceFactory(session=session, resources=resources)
    tenant, membership = await services.tenant_service.create_tenant(
        name=f"Workspace {slug}", slug=slug, owner=user
    )
    # create_tenant sets the tenant context; the rows below rely on it.

    website = services.client_websites.new(
        name=f"{slug} client",
        domain=f"{slug}-client.test",
        normalized_domain=f"{slug}-client.test",
        website_url=f"https://{slug}-client.test",
        description=f"The {slug} client business",
        industry="software",
        target_country="US",
        target_countries=["US"],
        target_language="en",
    )
    await session.flush()

    campaign = services.campaigns.new(
        client_website_id=website.id,
        name=f"{slug} campaign",
        status="ACTIVE",
        target_country="US",
        target_language="en",
        free_only=True,
        target_link_count=25,
    )
    await session.flush()

    free_publisher = services.publishers.new(
        domain=f"{slug}-freedir.test",
        normalized_domain=f"{slug}-freedir.test",
        website_url=f"https://{slug}-freedir.test",
        name=f"{slug} free directory",
        category=PublisherCategory.BUSINESS_DIRECTORY.value,
        country="US",
        language="en",
        submission_url=f"https://{slug}-freedir.test/submit",
        submission_method=SubmissionMethod.MANUAL.value,
        pricing_type=PricingType.FREE.value,
        status=PublisherStatus.QUALIFIED.value,
        quality_score=80,
        relevance_score=70,
        spam_score=5,
        authority_score=55,
    )
    paid_publisher = services.publishers.new(
        domain=f"{slug}-paiddir.test",
        normalized_domain=f"{slug}-paiddir.test",
        website_url=f"https://{slug}-paiddir.test",
        name=f"{slug} paid directory",
        category=PublisherCategory.BUSINESS_DIRECTORY.value,
        submission_method=SubmissionMethod.MANUAL.value,
        pricing_type=PricingType.PAID.value,
        status=PublisherStatus.QUALIFIED.value,
    )
    await session.flush()

    opportunity = services.opportunities.new(
        campaign_id=campaign.id,
        publisher_id=free_publisher.id,
        opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
        target_url=f"https://{slug}-client.test/",
        status=OpportunityStatus.SELECTED.value,
        priority=60,
        submission_url=free_publisher.submission_url,
    )
    await session.flush()

    return TenantFixture(
        tenant=tenant,
        owner=user,
        owner_membership=membership,
        client_website=website,
        campaign=campaign,
        free_publisher=free_publisher,
        paid_publisher=paid_publisher,
        opportunity=opportunity,
    )


@pytest_asyncio.fixture
async def tenants(
    session_factory: async_sessionmaker[TenantAwareSession],
    resources: AppResources,
    seeded_permissions: None,
) -> AsyncIterator[tuple[TenantFixture, TenantFixture]]:
    """Tenant A and tenant B, each with its own data. Cleaned up afterwards."""
    hasher = resources.password_hasher
    async with session_factory() as session:
        first = await _build_tenant(
            session=session,
            resources=resources,
            slug="tenant-a",
            email="owner-a@fixture.example.com",
            hasher=hasher,
        )
        await session.commit()

    async with session_factory() as session:
        second = await _build_tenant(
            session=session,
            resources=resources,
            slug="tenant-b",
            email="owner-b@fixture.example.com",
            hasher=hasher,
        )
        await session.commit()

    yield first, second

    # Deleting the tenants cascades to every tenant-owned row; the users are
    # global and are removed explicitly.
    async with session_factory() as session:
        for fixture in (first, second):
            tenant = await session.get(Tenant, fixture.tenant_id)
            if tenant is not None:
                await session.delete(tenant)
            user = await session.get(User, fixture.owner.id)
            if user is not None:
                await session.delete(user)
        await session.commit()


@pytest_asyncio.fixture
async def tenant_a(tenants: tuple[TenantFixture, TenantFixture]) -> TenantFixture:
    return tenants[0]


@pytest_asyncio.fixture
async def tenant_b(tenants: tuple[TenantFixture, TenantFixture]) -> TenantFixture:
    return tenants[1]


@pytest_asyncio.fixture
async def member_statuses() -> tuple[str, ...]:
    return tuple(status.value for status in MembershipStatus)

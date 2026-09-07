"""Curated seed-list discovery.

The zero-configuration provider: it needs no credential and no external call,
so a new workspace can run a discovery on day one and see the whole pipeline
work end to end.

The entries below are well-known directory *candidates*, not verified free
listings. Every one is emitted with ``submission_method`` and pricing left
unasserted, because whether a given directory currently accepts free listings
is a fact that changes and that only qualification can establish. Nothing here
becomes submittable until the qualification service has fetched the site and
confirmed a free submission path.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import PublisherCategory, SubmissionMethod
from app.integrations.discovery.base import (
    DiscoveredPublisher,
    DiscoveryProviderInfo,
    DiscoveryQuery,
)


@dataclass(frozen=True, slots=True)
class SeedEntry:
    """A starting candidate with the metadata needed to filter it."""

    website_url: str
    name: str
    category: PublisherCategory
    #: ``None`` means the directory is not country-specific.
    country: str | None = None
    language: str | None = "en"
    keywords: tuple[str, ...] = ()


#: A small, general-purpose starting set. A production deployment would grow
#: this per vertical, or lean on the search/AI providers instead.
SEED_ENTRIES: tuple[SeedEntry, ...] = (
    SeedEntry(
        "https://www.crunchbase.com",
        "Crunchbase",
        PublisherCategory.COMPANY_LISTING,
        keywords=("startup", "company", "funding", "business", "technology"),
    ),
    SeedEntry(
        "https://www.producthunt.com",
        "Product Hunt",
        PublisherCategory.STARTUP_DIRECTORY,
        keywords=("startup", "product", "software", "saas", "app", "technology"),
    ),
    SeedEntry(
        "https://alternativeto.net",
        "AlternativeTo",
        PublisherCategory.SOFTWARE_DIRECTORY,
        keywords=("software", "saas", "app", "tool", "alternative"),
    ),
    SeedEntry(
        "https://slashdot.org/software",
        "SourceForge / Slashdot Software",
        PublisherCategory.SOFTWARE_DIRECTORY,
        keywords=("software", "open source", "tool", "developer"),
    ),
    SeedEntry(
        "https://www.saashub.com",
        "SaaSHub",
        PublisherCategory.SOFTWARE_DIRECTORY,
        keywords=("saas", "software", "app", "tool", "b2b"),
    ),
    SeedEntry(
        "https://www.goodfirms.co",
        "GoodFirms",
        PublisherCategory.BUSINESS_DIRECTORY,
        keywords=("agency", "services", "b2b", "software", "development"),
    ),
    SeedEntry(
        "https://clutch.co",
        "Clutch",
        PublisherCategory.BUSINESS_DIRECTORY,
        keywords=("agency", "services", "b2b", "marketing", "development"),
    ),
    SeedEntry(
        "https://www.yelp.com",
        "Yelp",
        PublisherCategory.LOCAL_DIRECTORY,
        country="US",
        keywords=("local", "business", "restaurant", "service", "shop"),
    ),
    SeedEntry(
        "https://www.yellowpages.com",
        "Yellow Pages",
        PublisherCategory.LOCAL_DIRECTORY,
        country="US",
        keywords=("local", "business", "service", "trade"),
    ),
    SeedEntry(
        "https://www.thomsonlocal.com",
        "Thomson Local",
        PublisherCategory.LOCAL_DIRECTORY,
        country="GB",
        keywords=("local", "business", "service", "trade"),
    ),
    SeedEntry(
        "https://www.justdial.com",
        "Justdial",
        PublisherCategory.LOCAL_DIRECTORY,
        country="IN",
        keywords=("local", "business", "service", "shop"),
    ),
    SeedEntry(
        "https://www.indiamart.com",
        "IndiaMART",
        PublisherCategory.BUSINESS_DIRECTORY,
        country="IN",
        keywords=("b2b", "supplier", "manufacturer", "wholesale", "business"),
    ),
    SeedEntry(
        "https://www.trustpilot.com",
        "Trustpilot",
        PublisherCategory.REVIEW_PLATFORM,
        keywords=("review", "business", "ecommerce", "service"),
    ),
    SeedEntry(
        "https://www.g2.com",
        "G2",
        PublisherCategory.REVIEW_PLATFORM,
        keywords=("software", "saas", "b2b", "review", "tool"),
    ),
    SeedEntry(
        "https://www.capterra.com",
        "Capterra",
        PublisherCategory.SOFTWARE_DIRECTORY,
        keywords=("software", "saas", "b2b", "tool", "business"),
    ),
)


class SeedListDiscoveryProvider:
    """Filters the built-in candidate list. No credential, no network call."""

    info = DiscoveryProviderInfo(
        key="seed_list",
        name="Built-in directory list",
        description=(
            "A curated starting set of well-known directory candidates. Needs no "
            "credential. Candidates still require qualification before they can be "
            "submitted to."
        ),
        requires_credential=False,
    )

    async def search(self, query: DiscoveryQuery) -> list[DiscoveredPublisher]:
        wanted = {keyword.strip().lower() for keyword in query.keywords if keyword.strip()}
        results: list[tuple[int, SeedEntry]] = []

        for entry in SEED_ENTRIES:
            if query.category is not None and entry.category is not query.category:
                continue
            # A global directory (country None) is relevant to every market; a
            # country-specific one only to its own.
            if query.country and entry.country and entry.country != query.country:
                continue
            if query.language and entry.language and entry.language != query.language:
                continue

            overlap = len(wanted & set(entry.keywords)) if wanted else 0
            if wanted and overlap == 0:
                continue
            results.append((overlap, entry))

        # Best keyword overlap first, then a stable alphabetical order so the
        # same query returns the same page.
        results.sort(key=lambda item: (-item[0], item[1].name))

        return [
            DiscoveredPublisher(
                website_url=entry.website_url,
                name=entry.name,
                category=entry.category,
                country=entry.country,
                language=entry.language,
                submission_method=SubmissionMethod.UNKNOWN,
                source_metadata={"source": "seed_list", "keyword_overlap": overlap},
            )
            for overlap, entry in results[: query.limit]
        ]

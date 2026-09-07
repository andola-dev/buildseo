"""Discovery providers."""

from __future__ import annotations

import asyncio

import pytest

from app.core.enums import PublisherCategory
from app.integrations.discovery.base import DiscoveryQuery, PublisherDiscoveryProvider
from app.integrations.discovery.seed_list import SEED_ENTRIES, SeedListDiscoveryProvider

pytestmark = pytest.mark.unit


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def provider() -> SeedListDiscoveryProvider:
    return SeedListDiscoveryProvider()


class TestSeedList:
    def test_satisfies_the_protocol_and_needs_no_credential(
        self, provider: SeedListDiscoveryProvider
    ) -> None:
        # The zero-configuration path: a new workspace can run discovery on
        # day one.
        assert isinstance(provider, PublisherDiscoveryProvider)
        assert not provider.info.requires_credential

    def test_never_asserts_a_submission_method_or_pricing(
        self, provider: SeedListDiscoveryProvider
    ) -> None:
        # Whether a directory currently accepts free listings is a fact only
        # qualification can establish, so discovery must not claim it.
        results = run(provider.search(DiscoveryQuery(limit=50)))
        assert results
        assert all(row.submission_method.value == "UNKNOWN" for row in results)

    def test_honours_the_result_limit(self, provider: SeedListDiscoveryProvider) -> None:
        assert len(run(provider.search(DiscoveryQuery(limit=3)))) == 3

    def test_keyword_matching_filters_and_ranks(self, provider: SeedListDiscoveryProvider) -> None:
        results = run(provider.search(DiscoveryQuery(keywords=("saas", "software"), limit=5)))
        assert results
        overlaps = [row.source_metadata["keyword_overlap"] for row in results]
        assert overlaps == sorted(overlaps, reverse=True)

    def test_a_country_query_keeps_global_directories(
        self, provider: SeedListDiscoveryProvider
    ) -> None:
        # A global directory is relevant to every market; a country-specific
        # one only to its own.
        results = run(provider.search(DiscoveryQuery(country="IN", limit=50)))
        assert all(row.country in (None, "IN") for row in results)
        assert any(row.country == "IN" for row in results)

    def test_category_filtering(self, provider: SeedListDiscoveryProvider) -> None:
        results = run(
            provider.search(DiscoveryQuery(category=PublisherCategory.LOCAL_DIRECTORY, limit=50))
        )
        assert results
        assert all(row.category is PublisherCategory.LOCAL_DIRECTORY for row in results)

    def test_results_are_deterministic(self, provider: SeedListDiscoveryProvider) -> None:
        # The same query must return the same page, or paging is meaningless.
        first = [row.website_url for row in run(provider.search(DiscoveryQuery(limit=5)))]
        second = [row.website_url for row in run(provider.search(DiscoveryQuery(limit=5)))]
        assert first == second

    def test_the_seed_list_is_not_empty(self) -> None:
        assert len(SEED_ENTRIES) >= 10


class TestDiscoveryQuery:
    def test_serialises_for_the_discovery_run_row(self) -> None:
        query = DiscoveryQuery(
            keywords=("saas",), country="US", category=PublisherCategory.SOFTWARE_DIRECTORY
        )
        stored = query.as_dict()
        assert stored["keywords"] == ["saas"]
        assert stored["country"] == "US"
        assert stored["category"] == "SOFTWARE_DIRECTORY"
        # The MVP is free-only, and the query records that explicitly.
        assert stored["free_only"] is True

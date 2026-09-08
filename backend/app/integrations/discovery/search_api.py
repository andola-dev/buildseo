"""Search-API discovery (BYOK).

Speaks the SerpApi-compatible JSON shape, which several search vendors expose,
so one adapter covers a family of providers rather than one vendor. The tenant
supplies its own key; there is no platform key.

The queries built here look for *free listing* pages specifically ("submit
your business", "add your company", "free listing") rather than generic topical
results, because a link-building tool needs directories that accept
submissions, not just pages about a topic.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.config.logging import get_logger
from app.core.domains import is_public_host
from app.core.enums import SubmissionMethod
from app.core.exceptions import ProviderError
from app.core.http_client import SafeHttpClient
from app.integrations.discovery.base import (
    DiscoveredPublisher,
    DiscoveryProviderInfo,
    DiscoveryQuery,
)

logger = get_logger(__name__)

#: Phrases that identify a directory accepting submissions.
_INTENT_PHRASES: tuple[str, ...] = (
    '"submit your business"',
    '"add your business"',
    '"free business listing"',
    '"add your company"',
    '"submit your site"',
)

#: Hosts that are never listing directories, so they are dropped before they
#: cost a qualification fetch.
_EXCLUDED_HOSTS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "instagram.com",
        "pinterest.com",
        "reddit.com",
        "youtube.com",
        "tiktok.com",
        "medium.com",
        "wikipedia.org",
        "quora.com",
        "amazon.com",
        "ebay.com",
    }
)


class SearchApiDiscoveryProvider:
    """Discovers directories through a tenant's own search API key."""

    info = DiscoveryProviderInfo(
        key="search_api",
        name="Search API",
        description=(
            "Finds directories through a SerpApi-compatible search provider using "
            "the workspace's own API key. Queries target free-listing submission "
            "pages rather than generic topical results."
        ),
        requires_credential=True,
        credential_provider="serpapi",
    )

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        api_key: str,
        base_url: str = "https://serpapi.com",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _build_queries(self, query: DiscoveryQuery) -> list[str]:
        """Cross the caller's keywords with submission-intent phrases."""
        topics = [keyword.strip() for keyword in query.keywords if keyword.strip()] or [
            "business directory"
        ]
        phrases = _INTENT_PHRASES if query.free_only else ('"directory"',)
        return [f"{topic} {phrase}" for topic in topics[:4] for phrase in phrases[:3]]

    async def search(self, query: DiscoveryQuery) -> list[DiscoveredPublisher]:
        found: dict[str, DiscoveredPublisher] = {}

        for search_term in self._build_queries(query):
            if len(found) >= query.limit:
                break
            try:
                results = await self._fetch(search_term, query)
            except ProviderError:
                # One failing query must not lose the results already
                # gathered; the run is reported with whatever was found.
                logger.warning("search provider query failed", extra={"provider": self.info.key})
                continue

            for item in results:
                candidate = self._to_candidate(item, search_term)
                if candidate is None:
                    continue
                found.setdefault(candidate.website_url, candidate)
                if len(found) >= query.limit:
                    break

        return list(found.values())[: query.limit]

    async def _fetch(self, search_term: str, query: DiscoveryQuery) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "engine": "google",
            "q": search_term,
            "num": min(20, max(10, query.limit)),
            "api_key": self._api_key,
        }
        if query.country:
            params["gl"] = query.country.lower()
        if query.language:
            params["hl"] = query.language.split("-")[0].lower()

        # The key goes in the query string because that is the only form this
        # API family accepts. SafeHttpClient's error path strips query strings
        # before a URL reaches a log or an error body, so it does not escape.
        response = await self._client.get(f"{self._base_url}/search.json", params=params)
        if not response.is_success:
            raise ProviderError(
                "The search provider rejected the request",
                code="SEARCH_PROVIDER_ERROR",
                details={"provider_status": response.status_code},
            )
        body = response.json()
        organic = body.get("organic_results") if isinstance(body, dict) else None
        return [item for item in (organic or []) if isinstance(item, dict)]

    def _to_candidate(self, item: dict[str, Any], search_term: str) -> DiscoveredPublisher | None:
        link = str(item.get("link") or "").strip()
        if not link:
            return None

        parts = urlsplit(link)
        host = (parts.hostname or "").lower()
        if not host or not is_public_host(host):
            return None
        # Compare against the registrable tail so subdomains are excluded too.
        if any(host == excluded or host.endswith(f".{excluded}") for excluded in _EXCLUDED_HOSTS):
            return None

        origin = f"{parts.scheme}://{parts.netloc}"
        return DiscoveredPublisher(
            website_url=origin,
            name=str(item.get("title") or "").strip() or None,
            description=str(item.get("snippet") or "").strip() or None,
            # The deep link is where a submission form was found, so it is kept
            # as the submission URL candidate while the site root identifies
            # the publisher.
            submission_url=link if link != origin else None,
            submission_method=SubmissionMethod.UNKNOWN,
            source_metadata={
                "source": self.info.key,
                "query": search_term,
                "position": item.get("position"),
            },
        )

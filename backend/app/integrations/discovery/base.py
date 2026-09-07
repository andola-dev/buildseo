"""The publisher-discovery contract.

Discovery is deliberately behind a protocol rather than wired to one search
engine. The sources a link-building team wants change often — a search API
today, an SEO vendor's index tomorrow, an internal curated list, an LLM
brainstorm — and each has a completely different response shape. Normalising
them here means the discovery *service* only ever sees
:class:`DiscoveredPublisher` and the de-duplication and qualification logic
stays identical whatever the source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.enums import PublisherCategory, SubmissionMethod


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    """What the caller is looking for."""

    keywords: tuple[str, ...] = ()
    country: str | None = None
    language: str | None = None
    category: PublisherCategory | None = None
    limit: int = 25
    #: Always true in this MVP. Present so the intent is explicit in the
    #: provider contract rather than an unstated assumption.
    free_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form stored on the ``discovery_runs`` row."""
        return {
            "keywords": list(self.keywords),
            "country": self.country,
            "language": self.language,
            "category": self.category.value if self.category else None,
            "limit": self.limit,
            "free_only": self.free_only,
        }


@dataclass(frozen=True, slots=True)
class DiscoveredPublisher:
    """One candidate, normalised.

    Scores are absent on purpose: a discovery source is not trusted to grade a
    publisher. Everything here is a claim to be checked by the qualification
    service, which is why ``pricing_type`` is not part of this structure
    either — "is it actually free?" is a qualification question.
    """

    website_url: str
    name: str | None = None
    description: str | None = None
    category: PublisherCategory | None = None
    country: str | None = None
    language: str | None = None
    submission_url: str | None = None
    contact_url: str | None = None
    submission_method: SubmissionMethod = SubmissionMethod.UNKNOWN
    #: Provider-specific context kept for auditing the discovery.
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveryProviderInfo:
    """Describes a provider for ``GET /publishers/discovery-providers``."""

    key: str
    name: str
    description: str
    #: Whether the tenant must configure a BYOK credential to use it.
    requires_credential: bool
    #: The ``credentials.provider`` value it looks for, when it needs one.
    credential_provider: str | None = None


@runtime_checkable
class PublisherDiscoveryProvider(Protocol):
    """Finds candidate free-listing sites."""

    info: DiscoveryProviderInfo

    async def search(self, query: DiscoveryQuery) -> list[DiscoveredPublisher]:
        """Return candidates, best-effort.

        Implementations return fewer results rather than raising when a source
        is partially unavailable; a hard failure raises a
        :class:`~app.core.exceptions.ProviderError` so the discovery run is
        recorded as FAILED rather than as an empty success.
        """
        ...

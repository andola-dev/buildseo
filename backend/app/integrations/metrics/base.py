"""The SEO metrics contract.

Authority and traffic figures come from third-party vendors, each with its own
schema and its own pricing. Behind a protocol, a tenant that has no vendor
configured still gets a usable qualification — :class:`NullMetricsProvider`
returns "unknown", and the scoring model treats unknown authority as neutral
rather than as zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SiteMetrics:
    """Third-party strength metrics for one domain."""

    domain: str
    #: 0-100 normalised authority. ``None`` means unmeasured.
    authority_score: float | None = None
    organic_traffic: int | None = None
    referring_domains: int | None = None
    #: Vendor's own spam estimate, 0-100.
    spam_score: float | None = None
    provider: str = "none"

    @property
    def is_known(self) -> bool:
        return self.authority_score is not None or self.organic_traffic is not None


@runtime_checkable
class MetricsProvider(Protocol):
    """Looks up third-party metrics for a domain."""

    provider_key: str

    async def fetch(self, normalized_domain: str) -> SiteMetrics:
        """Return metrics, or an "unknown" result when unavailable.

        Must not raise for a domain the vendor has no data on: absent data is
        a normal outcome and scores neutral.
        """
        ...


class NullMetricsProvider:
    """Used when a workspace has configured no metrics vendor.

    Returning "unknown" rather than failing is deliberate: qualification must
    work on day one, before a tenant has bought an SEO data subscription.
    """

    provider_key = "none"

    async def fetch(self, normalized_domain: str) -> SiteMetrics:
        return SiteMetrics(domain=normalized_domain, provider=self.provider_key)

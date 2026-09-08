"""The crawler contract.

Qualification needs evidence about a site. Keeping that behind a protocol
means the polite HTTP fetcher used today can be replaced by a headless browser
(for JavaScript-rendered directories) or a third-party rendering service
without touching the scoring logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SiteSnapshot:
    """What a fetch learned about a site.

    Every field is optional/defaulted so a partial fetch still yields a
    scoreable snapshot: missing evidence lowers a score rather than aborting
    qualification.
    """

    url: str
    reachable: bool = False
    status_code: int | None = None
    tls_valid: bool = False
    title: str | None = None
    #: Lower-cased visible text, truncated. Used for keyword and intent
    #: matching only; never stored.
    text: str = ""
    #: A discovered "submit your listing" style path, if any.
    submission_path: str | None = None
    outbound_link_count: int | None = None
    #: True unless robots.txt or a meta-noindex says otherwise.
    indexable: bool = True
    #: Detected negative signals, e.g. "paid_links_offered".
    spam_signals: tuple[str, ...] = ()
    #: Whether a free submission path was found.
    free_listing_detected: bool = False
    #: Whether the page states that listings are paid.
    paid_listing_detected: bool = False
    #: Failure class when unreachable. Never a raw exception message.
    error: str | None = None
    notes: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class CrawlerProvider(Protocol):
    """Fetches a site and reports what it found."""

    async def fetch_site(self, url: str) -> SiteSnapshot:
        """Fetch and analyse ``url``.

        Implementations must not raise for an unreachable site: they return a
        snapshot with ``reachable=False`` and an ``error`` class, so a dead
        domain scores zero instead of failing the whole discovery run.
        """
        ...

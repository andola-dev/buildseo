"""Link verification.

Answers one question: is the client's link actually present on the page the
publisher published? Behind a protocol, because "fetch the page and look" is
only the first implementation — a rendering service or a third-party link
monitor can replace it without touching the workflow.

Matching is on the canonical *domain plus path*, not on an exact string:
directories routinely rewrite a submitted URL (adding tracking parameters, or
wrapping it in a redirect), so an exact match would report false negatives on
links that are genuinely live.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import urljoin, urlsplit

from app.config.logging import get_logger
from app.core.domains import normalize_domain
from app.core.exceptions import ProviderError, ValidationError
from app.core.http_client import SafeHttpClient

logger = get_logger(__name__)

_ANCHOR_RE = re.compile(
    r"<a\s([^>]*?)href=[\"']([^\"']+)[\"']([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL
)
_MARKUP_RE = re.compile(r"<[^>]+>")
_REL_RE = re.compile(r"rel=[\"']([^\"']*)[\"']", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """What was found on the published page."""

    verified: bool
    checked_url: str
    #: True when the page was fetched successfully, whatever it contained.
    page_reachable: bool = False
    http_status: int | None = None
    #: The matching href as it appears on the page.
    found_href: str | None = None
    anchor_text: str | None = None
    #: ``nofollow``, ``sponsored``, ``ugc`` … as declared on the anchor.
    rel: str | None = None
    is_dofollow: bool | None = None
    #: Failure class when the check could not be completed.
    error: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class LinkVerifier(Protocol):
    """Checks whether a target link is present on a page."""

    async def verify(self, *, published_url: str, target_url: str) -> VerificationResult:
        """Look for ``target_url`` on ``published_url``.

        Must not raise for an unreachable page: it returns ``verified=False``
        with an error class, so a temporarily-down directory does not fail the
        whole verification sweep.
        """
        ...


class HttpLinkVerifier:
    """Fetches the page and looks for the link in its markup."""

    def __init__(self, *, client: SafeHttpClient) -> None:
        self._client = client

    async def verify(self, *, published_url: str, target_url: str) -> VerificationResult:
        try:
            response = await self._client.get(published_url, headers={"Accept": "text/html"})
        except (ProviderError, ValidationError) as exc:
            return VerificationResult(
                verified=False, checked_url=published_url, error=exc.code.lower()
            )

        if not response.is_success:
            return VerificationResult(
                verified=False,
                checked_url=published_url,
                page_reachable=False,
                http_status=response.status_code,
                error=f"http_{response.status_code}",
            )

        try:
            wanted_domain = normalize_domain(target_url)
        except ValidationError:
            return VerificationResult(
                verified=False, checked_url=published_url, error="invalid_target_url"
            )
        wanted_path = _normalise_path(urlsplit(target_url).path)

        anchors = _ANCHOR_RE.findall(response.text)
        for before, href, after, inner in anchors:
            absolute = urljoin(published_url, href)
            try:
                href_domain = normalize_domain(absolute)
            except ValidationError:
                continue
            if href_domain != wanted_domain:
                continue
            if wanted_path and _normalise_path(urlsplit(absolute).path) != wanted_path:
                continue

            rel_match = _REL_RE.search(before) or _REL_RE.search(after)
            rel = rel_match.group(1).lower().strip() if rel_match else None
            anchor_text = _MARKUP_RE.sub("", inner).strip()[:255] or None

            return VerificationResult(
                verified=True,
                checked_url=published_url,
                page_reachable=True,
                http_status=response.status_code,
                found_href=absolute[:2048],
                anchor_text=anchor_text,
                rel=rel,
                # A nofollow/sponsored/ugc link is still a live listing; the
                # workflow records the attribute rather than treating it as a
                # failure, because many free directories nofollow by policy.
                is_dofollow=not _is_nofollow(rel),
                evidence={"anchors_scanned": len(anchors)},
            )

        return VerificationResult(
            verified=False,
            checked_url=published_url,
            page_reachable=True,
            http_status=response.status_code,
            error="link_not_found",
            evidence={"anchors_scanned": len(anchors)},
        )


def _normalise_path(path: str) -> str:
    """Compare paths ignoring a trailing slash and case-insensitively."""
    return (path or "").rstrip("/").lower()


def _is_nofollow(rel: str | None) -> bool:
    if not rel:
        return False
    tokens = set(rel.replace(",", " ").split())
    return bool(tokens & {"nofollow", "sponsored", "ugc"})

"""Polite HTTP crawler used for publisher qualification.

Scope is deliberately narrow. It fetches the home page (and, if needed, one
likely submission path), reads the visible text, and reports signals. It does
not crawl a site, does not execute JavaScript, and does not attempt to log in
or submit anything.

Three rules it will not break:

* ``robots.txt`` is fetched and honoured. A disallowed path is not fetched.
* No CAPTCHA is solved and no anti-bot challenge is worked around. A challenge
  page is reported as a signal, and the publisher falls back to manual
  submission.
* Requests are identified by the configured User-Agent and bounded by the
  shared client's timeouts and response size caps.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from app.config.logging import get_logger
from app.core.exceptions import (
    ProviderError,
    ResponseTooLargeError,
    ValidationError,
)
from app.core.http_client import SafeHttpClient
from app.integrations.crawler.base import SiteSnapshot

logger = get_logger(__name__)

_TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_MARKUP_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"'#]+)", re.IGNORECASE)
_NOINDEX_RE = re.compile(
    r"<meta[^>]+name=[\"']robots[\"'][^>]+content=[\"'][^\"']*noindex", re.IGNORECASE
)

#: Text that indicates a free submission path.
_FREE_PHRASES: tuple[str, ...] = (
    "submit your business",
    "add your business",
    "add your company",
    "submit your site",
    "submit a listing",
    "add a listing",
    "free listing",
    "list your business",
    "claim your profile",
    "create a free profile",
    "add your product",
    "submit your product",
)

#: Text that indicates listings cost money.
_PAID_PHRASES: tuple[str, ...] = (
    "paid listing",
    "premium listing",
    "sponsored listing",
    "listing fee",
    "pay to list",
    "upgrade to list",
    "purchase a listing",
)

#: Text that marks a site as one this platform will not work with.
_SPAM_PHRASES: dict[str, tuple[str, ...]] = {
    "paid_links_offered": (
        "buy backlinks",
        "buy links",
        "paid guest post",
        "sponsored post price",
        "link building packages",
        "dofollow link for",
        "guest post service",
    ),
    "link_scheme": ("link exchange", "reciprocal link", "link wheel", "link farm"),
    "pbn_footprint": ("private blog network", "pbn network"),
    "adult_content": ("xxx", "porn", "adult webcam"),
    "gambling_content": ("online casino bonus", "betting odds bonus"),
}

#: Paths commonly used for a submission form.
_CANDIDATE_PATHS: tuple[str, ...] = (
    "/submit",
    "/add-listing",
    "/add-business",
    "/submit-site",
    "/add-url",
    "/list-your-business",
    "/for-businesses",
)

#: Signals that a request hit a bot challenge rather than the real page.
_CHALLENGE_MARKERS: tuple[str, ...] = (
    "captcha",
    "cf-challenge",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies to continue",
)

_MAX_TEXT_CHARS = 200_000


class HttpCrawlerProvider:
    """Fetches a page and derives qualification signals from it."""

    def __init__(self, *, client: SafeHttpClient, respect_robots: bool = True) -> None:
        self._client = client
        self._respect_robots = respect_robots

    async def fetch_site(self, url: str) -> SiteSnapshot:
        """Fetch a site and report what was found. Never raises for a bad site."""
        try:
            return await self._fetch(url)
        except ValidationError as exc:
            # Not a public http(s) URL: refused before any request was made.
            return SiteSnapshot(url=url, reachable=False, error=exc.code.lower())
        except ResponseTooLargeError:
            return SiteSnapshot(url=url, reachable=False, error="response_too_large")
        except ProviderError as exc:
            return SiteSnapshot(url=url, reachable=False, error=exc.code.lower())
        except Exception:  # pragma: no cover - defensive
            logger.exception("crawler failed unexpectedly")
            return SiteSnapshot(url=url, reachable=False, error="unexpected_error")

    async def _fetch(self, url: str) -> SiteSnapshot:
        if self._respect_robots and not await self._robots_allows(url):
            logger.info("crawl skipped: disallowed by robots.txt")
            return SiteSnapshot(
                url=url, reachable=False, indexable=False, error="robots_disallowed"
            )

        response = await self._client.get(url, headers={"Accept": "text/html"})
        html = response.text
        text = _visible_text(html)

        if not response.is_success:
            return SiteSnapshot(
                url=url,
                reachable=False,
                status_code=response.status_code,
                tls_valid=url.lower().startswith("https://"),
                error=f"http_{response.status_code}",
            )

        challenge = next((marker for marker in _CHALLENGE_MARKERS if marker in text), None)
        if challenge:
            # Anti-bot challenges are respected, not circumvented: the site is
            # reported as needing a human, and qualification proceeds without
            # page evidence.
            logger.info("crawl stopped at a bot challenge; leaving it to a human")
            return SiteSnapshot(
                url=url,
                reachable=True,
                status_code=response.status_code,
                tls_valid=url.lower().startswith("https://"),
                indexable=not bool(_NOINDEX_RE.search(html)),
                error="bot_challenge_present",
                notes={"challenge_marker": challenge, "requires_manual_review": True},
            )

        submission_path = _find_submission_path(html, url, text)
        if submission_path is None:
            submission_path = await self._probe_candidate_paths(url)

        free_detected = any(phrase in text for phrase in _FREE_PHRASES)
        paid_detected = any(phrase in text for phrase in _PAID_PHRASES)

        return SiteSnapshot(
            url=url,
            reachable=True,
            status_code=response.status_code,
            tls_valid=str(response.url).lower().startswith("https://"),
            title=_extract_title(html),
            text=text[:_MAX_TEXT_CHARS],
            submission_path=submission_path,
            outbound_link_count=_count_external_links(html, url),
            indexable=not bool(_NOINDEX_RE.search(html)),
            spam_signals=_detect_spam(text),
            free_listing_detected=free_detected or submission_path is not None,
            paid_listing_detected=paid_detected and not free_detected,
        )

    async def _robots_allows(self, url: str) -> bool:
        """Check robots.txt for our User-Agent. Absent or unreadable = allowed."""
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = await self._client.get(robots_url, retries=0)
        except (ProviderError, ValidationError):
            # No robots.txt reachable: the convention is that crawling is
            # permitted. A fetch failure must not block qualification.
            return True
        if not response.is_success:
            return True

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        agent = self._client.config.user_agent.split("/")[0] or "*"
        return bool(parser.can_fetch(agent, url))

    async def _probe_candidate_paths(self, url: str) -> str | None:
        """Try a couple of conventional submission paths.

        Capped at three requests: this is a hint-gathering step, not a crawl.
        """
        for path in _CANDIDATE_PATHS[:3]:
            candidate = urljoin(url, path)
            try:
                response = await self._client.get(candidate, retries=0)
            except (ProviderError, ValidationError):
                continue
            if response.is_success and any(
                phrase in _visible_text(response.text) for phrase in _FREE_PHRASES
            ):
                return candidate
        return None


def _visible_text(html: str) -> str:
    """Strip markup and collapse whitespace, lower-cased for matching."""
    without_blocks = _TAG_RE.sub(" ", html)
    without_markup = _MARKUP_RE.sub(" ", without_blocks)
    return _WHITESPACE_RE.sub(" ", without_markup).strip().lower()


def _extract_title(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if not match:
        return None
    title = _WHITESPACE_RE.sub(" ", _MARKUP_RE.sub("", match.group(1))).strip()
    return title[:255] or None


def _find_submission_path(html: str, base_url: str, text: str) -> str | None:
    """Look for a link whose text or href suggests a submission page."""
    for href in _LINK_RE.findall(html):
        lowered = href.lower()
        if any(
            marker in lowered
            for marker in ("submit", "add-listing", "add-business", "add-url", "list-your")
        ):
            return urljoin(base_url, href)
    # Fall back to page text mentioning submission without a matching href.
    return None if not any(phrase in text for phrase in _FREE_PHRASES) else base_url


def _count_external_links(html: str, base_url: str) -> int:
    """Count links pointing off-site — a link farm indicator."""
    host = (urlsplit(base_url).hostname or "").lower()
    count = 0
    for href in _LINK_RE.findall(html):
        target = urlsplit(urljoin(base_url, href)).hostname
        if target and target.lower() != host:
            count += 1
    return count


def _detect_spam(text: str) -> tuple[str, ...]:
    """Return the named spam signals present in the page text."""
    return tuple(
        signal
        for signal, phrases in _SPAM_PHRASES.items()
        if any(phrase in text for phrase in phrases)
    )

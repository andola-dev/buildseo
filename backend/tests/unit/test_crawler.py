"""The qualification crawler.

The behavioural contract that matters most: it honours robots.txt, it stops at
anti-bot challenges instead of working around them, and it never raises for a
bad site — a dead domain must score zero, not fail a discovery run.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.http_client import HttpClientConfig, SafeHttpClient
from app.integrations.crawler.base import CrawlerProvider
from app.integrations.crawler.http_crawler import HttpCrawlerProvider

pytestmark = pytest.mark.unit

HOME = """<html><head><title> Free  Business Directory </title>
<meta name="robots" content="index,follow"></head><body>
<script>var promo = "buy backlinks cheap";</script>
<h1>Directory</h1><p>Submit your business for free today.</p>
<a href="/submit-site">Submit your site</a>
<a href="https://other.example/a">out1</a><a href="https://third.example/b">out2</a>
<a href="/internal">internal</a></body></html>"""

PAID = """<html><head><title>Paid Dir</title></head><body>
<p>Premium listing available. A listing fee applies.</p></body></html>"""

SPAM = """<html><body><p>We offer paid guest post placements and link exchange
packages. Buy backlinks cheap.</p></body></html>"""

CHALLENGE = """<html><body>Checking your browser before accessing. Please enable
JavaScript and cookies to continue. captcha</body></html>"""

NOINDEX = """<html><head><meta name="robots" content="noindex"></head>
<body>x</body></html>"""


def _handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if path == "/robots.txt":
        if host == "blocked.example":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        if host == "norobots.example":
            return httpx.Response(404)
        return httpx.Response(200, text="User-agent: *\nAllow: /")
    if host in ("good.example", "norobots.example") and path == "/":
        return httpx.Response(200, text=HOME)
    if host == "paid.example":
        return httpx.Response(200, text=PAID)
    if host == "spam.example":
        return httpx.Response(200, text=SPAM)
    if host == "challenge.example":
        return httpx.Response(200, text=CHALLENGE)
    if host == "noindex.example":
        return httpx.Response(200, text=NOINDEX)
    if host == "gone.example":
        return httpx.Response(404, text="nope")
    if host == "dead.example":
        raise httpx.ConnectError("refused")
    if host == "probe.example":
        if path == "/":
            return httpx.Response(200, text="<html><body>Nothing here</body></html>")
        if path == "/submit":
            return httpx.Response(200, text="<html><body>Add your business free</body></html>")
        return httpx.Response(404)
    return httpx.Response(404)


@pytest.fixture
def crawler() -> HttpCrawlerProvider:
    client = SafeHttpClient(
        HttpClientConfig(max_retries=0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    return HttpCrawlerProvider(client=client)


def run(coro):
    return asyncio.run(coro)


def test_satisfies_the_protocol(crawler: HttpCrawlerProvider) -> None:
    assert isinstance(crawler, CrawlerProvider)


class TestSignalExtraction:
    def test_reads_the_title_free_signal_and_submission_path(
        self, crawler: HttpCrawlerProvider
    ) -> None:
        snapshot = run(crawler.fetch_site("https://good.example/"))
        assert snapshot.reachable
        assert snapshot.status_code == 200
        assert snapshot.tls_valid
        assert snapshot.title == "Free Business Directory"
        assert snapshot.free_listing_detected
        assert not snapshot.paid_listing_detected
        assert snapshot.submission_path and "submit" in snapshot.submission_path
        assert snapshot.indexable

    def test_counts_only_external_links(self, crawler: HttpCrawlerProvider) -> None:
        # The link-farm indicator, so internal navigation must not inflate it.
        assert run(crawler.fetch_site("https://good.example/")).outbound_link_count == 2

    def test_script_contents_cannot_fabricate_a_spam_signal(
        self, crawler: HttpCrawlerProvider
    ) -> None:
        # The page's <script> contains "buy backlinks"; stripping script bodies
        # is what stops that being read as a spam signal.
        snapshot = run(crawler.fetch_site("https://good.example/"))
        assert snapshot.spam_signals == ()
        assert "buy backlinks" not in snapshot.text

    def test_detects_a_paid_listing(self, crawler: HttpCrawlerProvider) -> None:
        snapshot = run(crawler.fetch_site("https://paid.example/"))
        assert snapshot.paid_listing_detected
        assert not snapshot.free_listing_detected

    def test_detects_link_selling_signals(self, crawler: HttpCrawlerProvider) -> None:
        signals = run(crawler.fetch_site("https://spam.example/")).spam_signals
        assert "paid_links_offered" in signals
        assert "link_scheme" in signals

    def test_detects_a_noindex_directive(self, crawler: HttpCrawlerProvider) -> None:
        assert not run(crawler.fetch_site("https://noindex.example/")).indexable

    def test_probes_conventional_paths_when_the_home_page_links_none(
        self, crawler: HttpCrawlerProvider
    ) -> None:
        snapshot = run(crawler.fetch_site("https://probe.example/"))
        assert snapshot.submission_path == "https://probe.example/submit"


class TestPoliteness:
    def test_a_robots_disallow_stops_the_crawl(self, crawler: HttpCrawlerProvider) -> None:
        snapshot = run(crawler.fetch_site("https://blocked.example/"))
        assert not snapshot.reachable
        assert snapshot.error == "robots_disallowed"
        assert not snapshot.indexable

    def test_a_missing_robots_file_means_crawling_is_permitted(
        self, crawler: HttpCrawlerProvider
    ) -> None:
        assert run(crawler.fetch_site("https://norobots.example/")).reachable

    def test_an_anti_bot_challenge_is_respected_not_circumvented(
        self, crawler: HttpCrawlerProvider
    ) -> None:
        snapshot = run(crawler.fetch_site("https://challenge.example/"))
        assert snapshot.reachable
        assert snapshot.error == "bot_challenge_present"
        assert snapshot.notes.get("requires_manual_review") is True
        # No page evidence is claimed from a challenge page.
        assert not snapshot.free_listing_detected


class TestFailureIsNeverAnException:
    @pytest.mark.parametrize(
        ("url", "expected_error"),
        [
            ("https://gone.example/", "http_404"),
            ("https://dead.example/", "provider_unavailable"),
            ("http://169.254.169.254/latest/meta-data", "blocked_host"),
            ("http://127.0.0.1/", "blocked_host"),
        ],
    )
    def test_a_bad_site_returns_a_snapshot_rather_than_raising(
        self, crawler: HttpCrawlerProvider, url: str, expected_error: str
    ) -> None:
        snapshot = run(crawler.fetch_site(url))
        assert not snapshot.reachable
        assert snapshot.error == expected_error

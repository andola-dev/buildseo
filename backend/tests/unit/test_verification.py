"""Link verification."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.http_client import HttpClientConfig, SafeHttpClient
from app.submissions.verification import HttpLinkVerifier, LinkVerifier

pytestmark = pytest.mark.unit

# The publisher rewrote the submitted URL with a tracking parameter and marked
# the link nofollow — both entirely normal for a free directory.
LISTING_PAGE = """<html><body>
<a href="https://other.example/">other</a>
<a rel="nofollow" href="https://client.example/products?utm_source=dir">Client Brand</a>
</body></html>"""

DOFOLLOW_PAGE = '<html><body><a href="http://www.client.example/products/">Client</a></body></html>'
NO_LINK_PAGE = '<html><body><a href="https://someoneelse.example/">x</a></body></html>'


def _handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "dir.example":
        return httpx.Response(200, text=LISTING_PAGE)
    if host == "dofollow.example":
        return httpx.Response(200, text=DOFOLLOW_PAGE)
    if host == "nolink.example":
        return httpx.Response(200, text=NO_LINK_PAGE)
    if host == "gone.example":
        return httpx.Response(404)
    if host == "dead.example":
        raise httpx.ConnectError("no route")
    return httpx.Response(404)


@pytest.fixture
def verifier() -> HttpLinkVerifier:
    client = SafeHttpClient(
        HttpClientConfig(max_retries=0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    return HttpLinkVerifier(client=client)


def run(coro):
    return asyncio.run(coro)


def test_satisfies_the_protocol(verifier: HttpLinkVerifier) -> None:
    assert isinstance(verifier, LinkVerifier)


class TestPositiveMatches:
    def test_tracking_parameters_added_by_the_publisher_do_not_break_the_match(
        self, verifier: HttpLinkVerifier
    ) -> None:
        # Exact string matching would report a false negative on a link that
        # is genuinely live.
        result = run(
            verifier.verify(
                published_url="https://dir.example/listing/1",
                target_url="https://client.example/products",
            )
        )
        assert result.verified
        assert result.page_reachable
        assert result.anchor_text == "Client Brand"
        assert result.evidence["anchors_scanned"] == 2

    def test_www_scheme_and_trailing_slash_differences_still_match(
        self, verifier: HttpLinkVerifier
    ) -> None:
        result = run(
            verifier.verify(
                published_url="https://dofollow.example/p",
                target_url="https://client.example/products",
            )
        )
        assert result.verified


class TestRelAttribute:
    def test_a_nofollow_link_is_recorded_not_failed(self, verifier: HttpLinkVerifier) -> None:
        # Many free directories nofollow by policy; the listing still exists.
        result = run(
            verifier.verify(
                published_url="https://dir.example/listing/1",
                target_url="https://client.example/products",
            )
        )
        assert result.verified
        assert result.rel == "nofollow"
        assert result.is_dofollow is False

    def test_a_dofollow_link_is_detected(self, verifier: HttpLinkVerifier) -> None:
        result = run(
            verifier.verify(
                published_url="https://dofollow.example/p",
                target_url="https://client.example/products",
            )
        )
        assert result.rel is None
        assert result.is_dofollow is True


class TestNegativeMatches:
    def test_a_different_path_on_the_same_domain_is_not_a_match(
        self, verifier: HttpLinkVerifier
    ) -> None:
        # Otherwise any link to the client's homepage would "verify" every
        # deep-link submission.
        result = run(
            verifier.verify(
                published_url="https://dofollow.example/p",
                target_url="https://client.example/some-other-page",
            )
        )
        assert not result.verified
        assert result.error == "link_not_found"

    def test_a_page_without_the_link_reports_not_found(self, verifier: HttpLinkVerifier) -> None:
        result = run(
            verifier.verify(
                published_url="https://nolink.example/p",
                target_url="https://client.example/products",
            )
        )
        assert not result.verified
        assert result.page_reachable
        assert result.error == "link_not_found"


class TestFailuresNeverRaise:
    @pytest.mark.parametrize(
        ("published_url", "expected_error"),
        [
            ("https://gone.example/p", "http_404"),
            ("https://dead.example/p", "provider_unavailable"),
            ("http://127.0.0.1/", "blocked_host"),
        ],
    )
    def test_an_unreachable_page_reports_rather_than_raising(
        self, verifier: HttpLinkVerifier, published_url: str, expected_error: str
    ) -> None:
        # A temporarily-down directory must not fail a whole verification sweep.
        result = run(
            verifier.verify(published_url=published_url, target_url="https://client.example/")
        )
        assert not result.verified
        assert result.error == expected_error

    def test_an_invalid_target_url_is_reported(self, verifier: HttpLinkVerifier) -> None:
        result = run(
            verifier.verify(published_url="https://dir.example/listing/1", target_url="junk")
        )
        assert not result.verified
        assert result.error == "invalid_target_url"

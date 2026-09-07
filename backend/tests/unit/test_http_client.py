"""The shared outbound HTTP client.

Every provider and the crawler go through this, so its guards are the ones
protecting the platform from tenant-supplied URLs.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ResponseTooLargeError,
    ValidationError,
)
from app.core.http_client import HttpClientConfig, SafeHttpClient

pytestmark = pytest.mark.unit

CALLS: list[str] = []


def _handler(request: httpx.Request) -> httpx.Response:
    CALLS.append(str(request.url))
    path = request.url.path
    if path == "/ok":
        return httpx.Response(200, json={"hello": "world"})
    if path == "/big":
        return httpx.Response(200, content=b"x" * 200_000)
    if path == "/declared":
        return httpx.Response(200, content=b"x" * 10, headers={"content-length": "10"})
    if path == "/redirect-public":
        return httpx.Response(302, headers={"location": "https://example.org/ok"})
    if path == "/redirect-metadata":
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})
    if path == "/redirect-loop":
        return httpx.Response(302, headers={"location": "/redirect-loop"})
    if path == "/flaky":
        attempts = len([call for call in CALLS if call.endswith("/flaky")])
        return httpx.Response(200 if attempts > 2 else 503)
    if path == "/timeout":
        raise httpx.ConnectTimeout("slow")
    if path == "/down":
        raise httpx.ConnectError("refused")
    if path == "/bad-json":
        return httpx.Response(200, content=b"not json")
    return httpx.Response(404)


def make_client(**overrides) -> SafeHttpClient:
    defaults: dict = {"max_retries": 0, "max_response_bytes": 100_000}
    config = HttpClientConfig(**{**defaults, **overrides})
    return SafeHttpClient(
        config,
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler), follow_redirects=False),
    )


def run(coro):
    return asyncio.run(coro)


class TestSuccess:
    def test_reads_a_json_response(self) -> None:
        async def scenario() -> None:
            client = make_client()
            response = await client.get("https://example.com/ok")
            assert response.status_code == 200
            assert response.json() == {"hello": "world"}
            assert response.is_success
            assert response.elapsed_seconds >= 0
            await client.aclose()

        run(scenario())

    def test_malformed_json_becomes_a_provider_error(self) -> None:
        async def scenario() -> None:
            client = make_client()
            response = await client.get("https://example.com/bad-json")
            with pytest.raises(ProviderError):
                response.json()
            await client.aclose()

        run(scenario())


class TestSsrfGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/x",
            "http://localhost/x",
            "http://10.1.2.3/x",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/x",
            "http://service.internal/x",
        ],
    )
    def test_refuses_a_non_public_destination(self, url: str) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ValidationError) as excinfo:
                await client.get(url)
            assert excinfo.value.code == "BLOCKED_HOST"
            await client.aclose()

        run(scenario())

    def test_refuses_a_non_http_scheme(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ValidationError) as excinfo:
                await client.get("file:///etc/passwd")
            assert excinfo.value.code == "INVALID_URL"
            await client.aclose()

        run(scenario())

    def test_the_guard_is_re_applied_to_every_redirect_hop(self) -> None:
        # The important case: an allowed host redirecting to the cloud metadata
        # endpoint. Following redirects inside httpx would miss this.
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ValidationError) as excinfo:
                await client.get("https://example.com/redirect-metadata")
            assert excinfo.value.code == "BLOCKED_HOST"
            await client.aclose()

        run(scenario())

    def test_loopback_is_allowed_when_explicitly_disabled(self) -> None:
        # Tests that point at a local stub server need this escape hatch.
        async def scenario() -> None:
            client = make_client(enforce_public_hosts=False)
            assert (await client.get("http://127.0.0.1/ok")).status_code == 200
            await client.aclose()

        run(scenario())


class TestResponseSizeCap:
    def test_aborts_an_oversized_body_while_streaming(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ResponseTooLargeError):
                await client.get("https://example.com/big")
            await client.aclose()

        run(scenario())

    def test_rejects_an_oversized_declared_length_before_reading(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ResponseTooLargeError) as excinfo:
                await client.get("https://example.com/declared", max_response_bytes=5)
            assert excinfo.value.details["declared_bytes"] == 10
            await client.aclose()

        run(scenario())


class TestRedirects:
    def test_follows_a_redirect_to_an_allowed_host(self) -> None:
        async def scenario() -> None:
            client = make_client()
            response = await client.get("https://example.com/redirect-public")
            assert response.json() == {"hello": "world"}
            await client.aclose()

        run(scenario())

    def test_refuses_an_endless_redirect(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ProviderError, match=r"[Rr]edirect"):
                await client.get("https://example.com/redirect-loop")
            await client.aclose()

        run(scenario())


class TestRetries:
    def test_retries_a_retryable_status_and_then_succeeds(self) -> None:
        async def scenario() -> None:
            CALLS.clear()
            client = make_client(max_retries=3)
            response = await client.get("https://example.com/flaky")
            assert response.status_code == 200
            assert len(CALLS) == 3
            await client.aclose()

        run(scenario())


class TestTransportErrors:
    def test_a_timeout_becomes_a_provider_timeout(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ProviderTimeoutError) as excinfo:
                await client.get("https://example.com/timeout?secret=x", retries=0)
            # Query strings are stripped before a URL reaches an error body.
            assert "?" not in str(excinfo.value.details.get("url", ""))
            await client.aclose()

        run(scenario())

    def test_a_refused_connection_becomes_provider_unavailable(self) -> None:
        async def scenario() -> None:
            client = make_client()
            with pytest.raises(ProviderUnavailableError):
                await client.get("https://example.com/down", retries=0)
            await client.aclose()

        run(scenario())

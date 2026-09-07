"""One pooled async HTTP client for every outbound call.

A new ``httpx.AsyncClient`` per request would throw away connection reuse and
leak sockets, so a single client is created at application startup and shared.
On top of pooling this wrapper adds the things every caller would otherwise
have to remember:

* bounded timeouts (separate connect and total budgets),
* retries with exponential backoff and jitter, honouring ``Retry-After``,
* a hard cap on response size, enforced while streaming rather than after,
* manual redirect following so **every hop** is re-checked against the SSRF
  guard — tenant-supplied URLs must never be able to reach link-local metadata
  endpoints or private ranges,
* structured, provider-agnostic exceptions instead of raw ``httpx`` errors.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from app.config.logging import get_logger
from app.core.domains import is_public_host
from app.core.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ResponseTooLargeError,
    ValidationError,
)

logger = get_logger(__name__)

_RETRY_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class HttpClientConfig:
    """Transport limits and retry policy."""

    timeout_seconds: float = 15.0
    connect_timeout_seconds: float = 5.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    max_retries: int = 2
    max_response_bytes: int = 5 * 1024 * 1024
    follow_redirects: bool = True
    max_redirects: int = 5
    user_agent: str = "BuildSEO/0.1"
    #: Only disabled by tests that point at a loopback stub server.
    enforce_public_hosts: bool = True


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A fully-read, size-bounded response."""

    status_code: int
    url: str
    headers: dict[str, str]
    content: bytes
    elapsed_seconds: float

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        """Parse the body as JSON, raising a provider error on malformed data."""
        import json

        try:
            return json.loads(self.content)
        except ValueError as exc:
            raise ProviderError(
                "Provider returned a malformed JSON response",
                details={"status_code": self.status_code},
            ) from exc


class SafeHttpClient:
    """Shared, guarded wrapper around a single pooled ``httpx.AsyncClient``."""

    __slots__ = ("_client", "_config")

    def __init__(
        self, config: HttpClientConfig, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds, connect=config.connect_timeout_seconds),
            limits=httpx.Limits(
                max_connections=config.max_connections,
                max_keepalive_connections=config.max_keepalive_connections,
            ),
            headers={"User-Agent": config.user_agent},
            # Redirects are followed manually so each hop is re-validated.
            follow_redirects=False,
        )

    @classmethod
    def from_settings(cls, settings: Any) -> SafeHttpClient:
        return cls(
            HttpClientConfig(
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive_connections,
                max_retries=settings.http_max_retries,
                max_response_bytes=settings.http_max_response_bytes,
                follow_redirects=settings.http_follow_redirects,
                max_redirects=settings.http_max_redirects,
                user_agent=settings.http_user_agent,
            )
        )

    @property
    def config(self) -> HttpClientConfig:
        return self._config

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ api --

    async def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("POST", url, **kwargs)

    async def post_json(
        self, url: str, payload: Any, *, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> HttpResponse:
        merged = {"Content-Type": "application/json", "Accept": "application/json"}
        merged.update(headers or {})
        return await self.request("POST", url, json=payload, headers=merged, **kwargs)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: bytes | None = None,
        max_response_bytes: int | None = None,
        retries: int | None = None,
    ) -> HttpResponse:
        """Perform a guarded request and return the fully-read response.

        Raises:
            ValidationError: the URL, or a redirect target, is not a public
                http(s) destination.
            ProviderTimeoutError / ProviderUnavailableError / ProviderError:
                transport-level failures, after retries are exhausted.
            ResponseTooLargeError: the body exceeded the configured cap.
        """
        attempt_budget = self._config.max_retries if retries is None else retries
        size_cap = max_response_bytes or self._config.max_response_bytes
        current_url = url
        redirects = 0
        last_error: Exception | None = None

        while True:
            self._assert_safe_url(current_url)
            for attempt in range(attempt_budget + 1):
                try:
                    response = await self._send_once(
                        method,
                        current_url,
                        headers=headers,
                        params=params,
                        json=json,
                        content=content,
                        size_cap=size_cap,
                    )
                except (ProviderTimeoutError, ProviderUnavailableError) as exc:
                    last_error = exc
                    if attempt >= attempt_budget:
                        raise
                    await self._sleep_backoff(attempt)
                    continue

                if response.status_code in _RETRY_STATUS_CODES and attempt < attempt_budget:
                    await self._sleep_backoff(attempt, response.headers.get("retry-after"))
                    continue

                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not self._config.follow_redirects or not location:
                        return response
                    if redirects >= self._config.max_redirects:
                        raise ProviderError(
                            "Too many redirects",
                            details={"max_redirects": self._config.max_redirects},
                        )
                    redirects += 1
                    current_url = str(httpx.URL(current_url).join(location))
                    # Per RFC 9110, a redirected non-GET becomes a GET without a body.
                    if response.status_code in (301, 302, 303) and method.upper() != "HEAD":
                        method, json, content = "GET", None, None
                    break  # re-enter the outer loop to re-validate the new host

                return response
            else:  # pragma: no cover - defensive; loop always returns or raises
                if last_error:
                    raise last_error
                raise ProviderError("Request failed without a response")

    # -------------------------------------------------------------- internals --

    async def _send_once(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        params: dict[str, Any] | None,
        json: Any | None,
        content: bytes | None,
        size_cap: int,
    ) -> HttpResponse:
        request = self._client.build_request(
            method, url, headers=headers, params=params, json=json, content=content
        )
        started = time.monotonic()
        try:
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(details={"url": _safe_url(url)}) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(details={"url": _safe_url(url)}) from exc

        try:
            declared = response.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > size_cap:
                raise ResponseTooLargeError(
                    details={"limit_bytes": size_cap, "declared_bytes": int(declared)}
                )

            buffer = bytearray()
            async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                buffer.extend(chunk)
                if len(buffer) > size_cap:
                    raise ResponseTooLargeError(details={"limit_bytes": size_cap})
            body = bytes(buffer)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(details={"url": _safe_url(url)}) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(details={"url": _safe_url(url)}) from exc
        finally:
            await response.aclose()

        return HttpResponse(
            status_code=response.status_code,
            url=str(response.request.url),
            headers={key.lower(): value for key, value in response.headers.items()},
            content=body,
            elapsed_seconds=time.monotonic() - started,
        )

    def _assert_safe_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ValidationError(
                "Only http and https URLs may be fetched",
                code="INVALID_URL",
                details={"scheme": parts.scheme},
            )
        host = parts.hostname
        if not host:
            raise ValidationError("URL must include a host", code="INVALID_URL")
        if self._config.enforce_public_hosts and not is_public_host(host):
            # Blocks loopback, RFC1918, link-local (169.254.169.254) and friends.
            raise ValidationError(
                "Refusing to fetch a non-public address",
                code="BLOCKED_HOST",
                details={"host": host},
            )

    async def _sleep_backoff(self, attempt: int, retry_after: str | None = None) -> None:
        """Exponential backoff with jitter, capped, honouring ``Retry-After``."""
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), 30.0)
        else:
            delay = min(2.0**attempt * 0.25, 8.0)
        await asyncio.sleep(delay * (0.5 + random.random() / 2))  # noqa: S311 - jitter only


def _safe_url(url: str) -> str:
    """Strip query strings and userinfo before a URL reaches a log or an error."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"

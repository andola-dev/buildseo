"""Shared HTTP plumbing for AI providers.

Every adapter speaks raw HTTP through the shared :class:`SafeHttpClient` rather
than a vendor SDK. That is a deliberate architectural choice for a BYOK
platform:

* one connection pool, one timeout policy, one retry policy and one response
  size cap for every provider, instead of each SDK's own;
* no per-vendor dependency to keep up to date, and no SDK that expects a
  process-wide API key when keys are per tenant;
* credentials stay in a header we control, and error handling can guarantee
  that a provider's response body — which frequently echoes the submitted key
  back in an error message — never reaches a log or an API response.
"""

from __future__ import annotations

import time
from typing import Any

from app.config.logging import get_logger
from app.core.exceptions import (
    ProviderError,
    ProviderUnavailableError,
)
from app.core.http_client import HttpResponse, SafeHttpClient

logger = get_logger(__name__)

#: Provider statuses that mean "the tenant's key is wrong", which the caller
#: turns into a CredentialStatus of INVALID rather than a retry.
_CREDENTIAL_STATUSES = frozenset({401, 403})


class HttpAIProvider:
    """Base class holding the request/error handling every adapter shares."""

    provider_key: str = "http"

    def __init__(self, *, client: SafeHttpClient, api_key: str, base_url: str) -> None:
        self._client = client
        # Held only in memory, only for the lifetime of the request that
        # resolved it. Never logged, never returned, never persisted.
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _post_json(
        self, path: str, payload: dict[str, Any], *, headers: dict[str, str]
    ) -> tuple[dict[str, Any], int]:
        """POST JSON and return the decoded body plus elapsed milliseconds."""
        started = time.monotonic()
        response = await self._client.post_json(f"{self._base_url}{path}", payload, headers=headers)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if not response.is_success:
            raise self._error_for(response)

        body = response.json()
        if not isinstance(body, dict):
            raise ProviderError(
                f"{self.provider_key} returned an unexpected response shape",
                code="PROVIDER_BAD_RESPONSE",
            )
        return body, elapsed_ms

    def _error_for(self, response: HttpResponse) -> ProviderError:
        """Map a provider status onto a normalised error.

        The provider's response body is deliberately discarded: several
        providers include the submitted API key (or a prefix of it) in error
        messages, so echoing the body would leak a tenant's credential into
        logs and API responses. Only the status code is retained.
        """
        status = response.status_code
        logger.warning(
            "AI provider request failed",
            extra={"provider": self.provider_key, "provider_status": status},
        )

        if status in _CREDENTIAL_STATUSES:
            return ProviderError(
                f"The configured {self.provider_key} credential was rejected",
                code="PROVIDER_CREDENTIAL_REJECTED",
                status_code=422,
                details={"provider": self.provider_key, "provider_status": status},
            )
        if status == 429:
            return ProviderError(
                f"{self.provider_key} rate limit reached; try again shortly",
                code="PROVIDER_RATE_LIMITED",
                status_code=429,
                details={"provider": self.provider_key},
            )
        if status >= 500:
            return ProviderUnavailableError(
                f"{self.provider_key} is temporarily unavailable",
                details={"provider": self.provider_key, "provider_status": status},
            )
        return ProviderError(
            f"{self.provider_key} rejected the request",
            code="PROVIDER_REQUEST_REJECTED",
            details={"provider": self.provider_key, "provider_status": status},
        )

    @staticmethod
    def _require_text(text: str | None, provider: str) -> str:
        """Reject an empty completion rather than storing a blank draft."""
        if not text or not text.strip():
            raise ProviderError(
                f"{provider} returned an empty completion",
                code="PROVIDER_EMPTY_RESPONSE",
                details={"provider": provider},
            )
        return text.strip()

"""Credential verification.

Probes a stored credential with the smallest possible provider call so a
workspace finds out immediately that a key is wrong, rather than discovering it
when a content generation fails.

Marking a rejected key ``INVALID`` matters operationally: without it, every
later request retries a key the provider has already refused, which is both
slow and impolite to the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config.logging import get_logger
from app.core.enums import CredentialProviderType, CredentialStatus
from app.core.exceptions import ProviderError
from app.core.http_client import SafeHttpClient
from app.credentials.service import CredentialService
from app.integrations.ai.base import GenerationRequest
from app.integrations.ai.providers import DEFAULT_MODELS
from app.models.credentials import Credential

logger = get_logger(__name__)

#: A one-token probe: enough to prove the key authenticates, cheap enough to
#: run on every credential write.
_PROBE_PROMPT = "ping"
_PROBE_MAX_TOKENS = 8


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """Result of probing a credential."""

    verified: bool
    #: A failure *class* only. The provider's response body is never surfaced,
    #: because several vendors echo the submitted key back in error messages.
    error_code: str | None = None
    checked_at: datetime | None = None
    #: True when this provider type cannot be probed, so the status is unchanged.
    skipped: bool = False


class CredentialVerificationService:
    """Verifies a credential against its provider."""

    def __init__(self, *, credentials: CredentialService, http_client: SafeHttpClient) -> None:
        self._credentials = credentials
        self._http = http_client

    async def verify(self, credential: Credential) -> tuple[Credential, VerificationOutcome]:
        """Probe ``credential`` and record the outcome on the row."""
        # Import here to avoid a cycle: the factory imports the credential
        # service, which this module also imports.
        from app.integrations.ai.factory import PROVIDER_CLASSES

        if credential.provider_type != CredentialProviderType.AI.value:
            # Search and SEO vendors have no uniform cheap probe; treating an
            # un-probeable credential as broken would be worse than leaving it
            # as configured.
            return credential, VerificationOutcome(
                verified=False, skipped=True, error_code="provider_not_verifiable"
            )

        adapter = PROVIDER_CLASSES.get(credential.provider)
        model = DEFAULT_MODELS.get(credential.provider)
        if adapter is None or model is None:
            return credential, VerificationOutcome(
                verified=False, skipped=True, error_code="no_probe_available"
            )

        try:
            _, secret = await self._credentials.get_secret_for_credential(credential.id)
            base_url = CredentialService.metadata_base_url(credential)
            kwargs: dict[str, object] = {"client": self._http, "api_key": secret}
            if base_url:
                kwargs["base_url"] = base_url
            provider = adapter(**kwargs)
            await provider.generate(
                GenerationRequest(
                    prompt=_PROBE_PROMPT,
                    model=model,
                    max_tokens=_PROBE_MAX_TOKENS,
                    temperature=0.0,
                )
            )
        except ProviderError as exc:
            logger.info(
                "credential verification failed",
                extra={"provider": credential.provider, "error_code": exc.code},
            )
            updated = await self._credentials.mark_verification(
                credential, verified=False, error_code=exc.code
            )
            return updated, VerificationOutcome(
                verified=False, error_code=exc.code, checked_at=datetime.now(UTC)
            )

        updated = await self._credentials.mark_verification(credential, verified=True)
        return updated, VerificationOutcome(
            verified=True, checked_at=updated.last_verified_at or datetime.now(UTC)
        )

    @staticmethod
    def status_of(credential: Credential) -> str:
        return credential.status or CredentialStatus.CONFIGURED.value

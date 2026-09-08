"""Per-tenant AI provider resolution.

The seam that makes "switch this tenant from OpenAI to Anthropic" a row
update. Callers ask for a *purpose*:

    provider, config = await factory.for_purpose(AiPurpose.CONTENT_GENERATION)

and receive a configured adapter plus the model to use. No service names a
vendor, so a new provider needs an adapter class and a configuration row —
nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.logging import get_logger
from app.core.enums import AiProvider, AiPurpose
from app.core.exceptions import CredentialNotConfiguredError, ProviderNotSupportedError
from app.core.http_client import SafeHttpClient
from app.credentials.service import CredentialService
from app.integrations.ai.base import AIProvider
from app.integrations.ai.providers import (
    AnthropicProvider,
    CustomOpenAICompatibleProvider,
    GeminiProvider,
    OpenAIProvider,
    OpenRouterProvider,
)
from app.models.credentials import TenantAiConfig
from app.repositories.credentials import TenantAiConfigRepository

logger = get_logger(__name__)

#: Provider key -> adapter class. Extending the platform means adding a row.
PROVIDER_CLASSES: dict[str, type] = {
    AiProvider.OPENAI.value: OpenAIProvider,
    AiProvider.ANTHROPIC.value: AnthropicProvider,
    AiProvider.GEMINI.value: GeminiProvider,
    AiProvider.OPENROUTER.value: OpenRouterProvider,
    AiProvider.CUSTOM.value: CustomOpenAICompatibleProvider,
}


@dataclass(frozen=True, slots=True)
class ResolvedProvider:
    """A ready-to-use adapter plus the configuration that selected it."""

    provider: AIProvider
    config: TenantAiConfig

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def provider_key(self) -> str:
        return self.config.provider


class AIProviderFactory:
    """Builds a provider adapter from a tenant's stored configuration."""

    def __init__(
        self,
        *,
        configs: TenantAiConfigRepository,
        credentials: CredentialService,
        http_client: SafeHttpClient,
    ) -> None:
        self._configs = configs
        self._credentials = credentials
        self._http = http_client

    async def for_purpose(self, purpose: AiPurpose | str) -> ResolvedProvider:
        """Resolve the provider a tenant has chosen for ``purpose``."""
        key = purpose.value if isinstance(purpose, AiPurpose) else str(purpose)
        config = await self._configs.get_default_for_purpose(key)
        if config is None:
            raise CredentialNotConfiguredError(
                f"No AI provider is configured for '{key}' in this workspace. "
                "Configure one with PUT /api/v1/ai/configs.",
                code="AI_PROVIDER_NOT_CONFIGURED",
                details={"purpose": key},
            )
        return ResolvedProvider(provider=await self.build(config), config=config)

    async def build(self, config: TenantAiConfig) -> AIProvider:
        """Instantiate the adapter for one configuration row."""
        adapter = PROVIDER_CLASSES.get(config.provider)
        if adapter is None:
            raise ProviderNotSupportedError(
                f"Provider '{config.provider}' has no adapter",
                details={"provider": config.provider},
            )

        base_url = ""
        api_key = ""
        if config.credential_id is not None:
            credential, api_key = await self._credentials.get_secret_for_credential(
                config.credential_id
            )
            base_url = CredentialService.metadata_base_url(credential)
        elif config.provider != AiProvider.CUSTOM.value:
            # Only a self-hosted custom endpoint may run without a credential.
            raise CredentialNotConfiguredError(
                f"The '{config.provider}' configuration has no credential attached",
                details={"provider": config.provider, "purpose": config.purpose},
            )
        else:
            base_url = str(config.parameters.get("base_url", ""))

        kwargs: dict[str, object] = {"client": self._http, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        provider = adapter(**kwargs)

        logger.debug(
            "resolved AI provider",
            extra={"provider": config.provider, "purpose": config.purpose},
        )
        return provider  # type: ignore[no-any-return]

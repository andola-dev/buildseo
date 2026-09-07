"""Discovery provider registry.

Resolves a provider key to a configured instance, reporting which providers a
workspace can actually use — a provider needing a credential the tenant has
not configured is listed as unavailable rather than failing at call time.
"""

from __future__ import annotations

from app.config.logging import get_logger
from app.core.enums import AiPurpose
from app.core.exceptions import CredentialNotConfiguredError, ProviderNotSupportedError
from app.core.http_client import SafeHttpClient
from app.credentials.service import CredentialService
from app.integrations.ai.factory import AIProviderFactory
from app.integrations.discovery.ai_discovery import AiDiscoveryProvider
from app.integrations.discovery.base import (
    DiscoveryProviderInfo,
    PublisherDiscoveryProvider,
)
from app.integrations.discovery.search_api import SearchApiDiscoveryProvider
from app.integrations.discovery.seed_list import SeedListDiscoveryProvider
from app.repositories.credentials import CredentialRepository

logger = get_logger(__name__)

PROVIDER_INFOS: tuple[DiscoveryProviderInfo, ...] = (
    SeedListDiscoveryProvider.info,
    SearchApiDiscoveryProvider.info,
    AiDiscoveryProvider.info,
)

DEFAULT_PROVIDER_KEY = SeedListDiscoveryProvider.info.key


class DiscoveryProviderRegistry:
    """Builds discovery providers for the active workspace."""

    def __init__(
        self,
        *,
        http_client: SafeHttpClient,
        credentials: CredentialService,
        credential_repository: CredentialRepository,
        ai_factory: AIProviderFactory,
    ) -> None:
        self._http = http_client
        self._credentials = credentials
        self._credential_repository = credential_repository
        self._ai_factory = ai_factory

    async def resolve(self, key: str) -> PublisherDiscoveryProvider:
        """Instantiate the provider identified by ``key``."""
        if key == SeedListDiscoveryProvider.info.key:
            return SeedListDiscoveryProvider()

        if key == SearchApiDiscoveryProvider.info.key:
            provider_name = SearchApiDiscoveryProvider.info.credential_provider or "serpapi"
            _, api_key = await self._credentials.resolve_for_provider(provider_name)
            return SearchApiDiscoveryProvider(client=self._http, api_key=api_key)

        if key == AiDiscoveryProvider.info.key:
            resolved = await self._ai_factory.for_purpose(AiPurpose.DISCOVERY)
            return AiDiscoveryProvider(provider=resolved.provider, model=resolved.model)

        raise ProviderNotSupportedError(
            f"Unknown discovery provider '{key}'",
            details={
                "provider": key,
                "available": [info.key for info in PROVIDER_INFOS],
            },
        )

    async def availability(self) -> list[dict[str, object]]:
        """Describe every provider and whether this workspace can use it."""
        rows: list[dict[str, object]] = []
        for info in PROVIDER_INFOS:
            available = True
            if info.requires_credential:
                available = await self._has_credential_for(info.key)
            rows.append(
                {
                    "key": info.key,
                    "name": info.name,
                    "description": info.description,
                    "requires_credential": info.requires_credential,
                    "available": available,
                }
            )
        return rows

    async def _has_credential_for(self, key: str) -> bool:
        """Whether the prerequisite credential/configuration exists."""
        if key == SearchApiDiscoveryProvider.info.key:
            provider_name = SearchApiDiscoveryProvider.info.credential_provider or "serpapi"
            return (
                await self._credential_repository.get_usable_for_provider(provider_name)
            ) is not None
        if key == AiDiscoveryProvider.info.key:
            try:
                await self._ai_factory.for_purpose(AiPurpose.DISCOVERY)
            except CredentialNotConfiguredError:
                return False
            return True
        return True

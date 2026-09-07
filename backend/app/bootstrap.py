"""Composition root.

Everything with a process lifetime is constructed exactly once, here, and
handed to the rest of the application. FastAPI dependencies read from this
container instead of module-level globals, so there is no mutable global state
and a test can build an isolated container with fakes substituted.

The worker entrypoint builds the same container, which is why services never
reach for ``request.app.state`` themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config.settings import Settings
from app.core.crypto.envelope import EnvelopeEncryptionService
from app.core.crypto.keys import EnvMasterKeyProvider, KeyProvider
from app.core.http_client import SafeHttpClient
from app.core.rate_limit import InMemoryRateLimiter, NullRateLimiter, RateLimiter
from app.core.security.jwt import JwtService
from app.core.security.password import PasswordHasher
from app.db.session import TenantAwareSession, create_engine, create_session_factory


@dataclass(slots=True)
class AppResources:
    """Process-wide singletons."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[TenantAwareSession]
    http_client: SafeHttpClient
    rate_limiter: RateLimiter
    key_provider: KeyProvider
    encryption: EnvelopeEncryptionService
    password_hasher: PasswordHasher
    jwt_service: JwtService

    async def aclose(self) -> None:
        """Release sockets and pooled connections in reverse creation order."""
        await self.http_client.aclose()
        await self.engine.dispose()


def build_resources(settings: Settings, *, engine: AsyncEngine | None = None) -> AppResources:
    """Construct the container. ``engine`` may be injected by tests."""
    db_engine = engine or create_engine(settings)
    key_provider = EnvMasterKeyProvider.from_settings(settings)

    return AppResources(
        settings=settings,
        engine=db_engine,
        session_factory=create_session_factory(db_engine),
        http_client=SafeHttpClient.from_settings(settings),
        rate_limiter=(InMemoryRateLimiter() if settings.rate_limit_enabled else NullRateLimiter()),
        key_provider=key_provider,
        encryption=EnvelopeEncryptionService(key_provider),
        password_hasher=PasswordHasher.from_settings(settings),
        jwt_service=JwtService(
            secret=settings.jwt_secret.get_secret_value(),
            algorithm=settings.jwt_algorithm,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            access_token_ttl=timedelta(minutes=settings.jwt_access_token_expire_minutes),
            leeway_seconds=settings.jwt_leeway_seconds,
        ),
    )

"""Async engine, session factory and the tenant-aware session.

Everything is asyncio: ``asyncpg`` under SQLAlchemy's async engine. There is no
synchronous ``Session`` anywhere in the application.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.exceptions import TenantContextMissingError
from app.db.context import apply_tenant_context

logger = get_logger(__name__)


class TenantAwareSession(AsyncSession):
    """An ``AsyncSession`` that remembers its tenant context and reasserts it.

    ``SET LOCAL`` dies with its transaction, which is exactly what we want for
    pool hygiene — but it also means a mid-request ``commit()`` would leave the
    *next* statement running with no tenant context. Rather than rely on every
    service to avoid that, this session re-applies the context immediately
    after each commit, so a tenant-scoped session can never silently continue
    unscoped.
    """

    _tenant_id: UUID | None
    _user_id: UUID | None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tenant_id = None
        self._user_id = None

    @property
    def tenant_id(self) -> UUID | None:
        return self._tenant_id

    @property
    def user_id(self) -> UUID | None:
        return self._user_id

    async def set_tenant_context(
        self, *, tenant_id: UUID | None, user_id: UUID | None = None
    ) -> None:
        """Bind this session to a tenant and apply it to the transaction."""
        self._tenant_id = tenant_id
        self._user_id = user_id
        await apply_tenant_context(self, tenant_id=tenant_id, user_id=user_id)

    def require_tenant_id(self) -> UUID:
        """Return the active tenant, or fail loudly.

        Repositories call this instead of accepting a tenant id argument, so a
        tenant-scoped query cannot be issued on an unbound session.
        """
        if self._tenant_id is None:
            raise TenantContextMissingError()
        return self._tenant_id

    async def commit(self) -> None:
        await super().commit()
        if self._tenant_id is not None or self._user_id is not None:
            await apply_tenant_context(self, tenant_id=self._tenant_id, user_id=self._user_id)

    async def rollback(self) -> None:
        await super().rollback()
        if self._tenant_id is not None or self._user_id is not None:
            await apply_tenant_context(self, tenant_id=self._tenant_id, user_id=self._user_id)


def create_engine(settings: Settings, *, url: str | None = None) -> AsyncEngine:
    """Build the async engine with pool and server settings from config."""
    server_settings: dict[str, str] = {"application_name": settings.app_name}
    if settings.db_statement_timeout_ms > 0:
        # Keeps a pathological query from pinning a pooled connection forever.
        server_settings["statement_timeout"] = str(settings.db_statement_timeout_ms)

    return create_async_engine(
        url or settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=settings.db_pool_pre_ping,
        connect_args={"server_settings": server_settings},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[TenantAwareSession]:
    """Session factory producing tenant-aware sessions.

    ``expire_on_commit=False`` keeps ORM objects usable after the request's
    commit, so response serialisation does not trigger a lazy reload against a
    transaction whose tenant context has already been discarded.
    """
    return async_sessionmaker(
        bind=engine,
        class_=TenantAwareSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[TenantAwareSession],
    *,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
) -> AsyncIterator[TenantAwareSession]:
    """Unit of work: commit on success, roll back on failure, always close.

    Used by workers and scripts; HTTP requests go through the equivalent
    FastAPI dependency so the session's lifetime matches the request's.
    """
    session = factory()
    try:
        if tenant_id is not None or user_id is not None:
            await session.set_tenant_context(tenant_id=tenant_id, user_id=user_id)
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()

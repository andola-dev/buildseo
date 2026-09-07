"""Database session dependencies.

Two flavours, and the distinction is the heart of the isolation model:

``UnscopedSessionDep``
    No tenant context. Only for pre-tenant work — login, token refresh,
    listing the tenants a user may enter, creating a workspace. Reaches only
    the global identity tables, which carry no ``tenant_id``.

``TenantSessionDep``
    Tenant context applied from a *validated* membership before the first
    domain query runs. Every tenant-owned repository requires one of these, so
    a request cannot touch tenant data without having proved membership.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from app.api.dependencies.core import ResourcesDep
from app.db.session import TenantAwareSession


async def get_unscoped_session(resources: ResourcesDep) -> AsyncIterator[TenantAwareSession]:
    """Yield a session with **no** tenant context (default-deny under RLS).

    Because no context is set, ``app.current_tenant_id`` is NULL and every RLS
    policy evaluates to false — so even if this session were handed to a
    tenant-owned repository by mistake, PostgreSQL returns nothing.
    """
    session = resources.session_factory()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


UnscopedSessionDep = Annotated[TenantAwareSession, Depends(get_unscoped_session)]

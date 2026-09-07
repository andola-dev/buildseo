"""Service-graph dependencies.

Two flavours mirroring the session split:

``ServicesDep``
    Built on the tenant-scoped session. What every domain endpoint uses.

``UnscopedServicesDep``
    Built on the unscoped session, for the pre-tenant flows (registration,
    login, refresh, workspace creation and listing).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.core import ResourcesDep
from app.api.dependencies.db import UnscopedSessionDep
from app.api.dependencies.tenant import TenantContextDep, TenantSessionDep
from app.auth.service import AuthService
from app.services.factory import ServiceFactory


async def get_services(
    session: TenantSessionDep,
    resources: ResourcesDep,
    context: TenantContextDep,
) -> ServiceFactory:
    """Assemble services around the tenant-scoped session.

    The workspace's ``settings`` are passed through so tenant-tunable
    behaviour (currently the scoring weights) reaches the services that use it.
    """
    return ServiceFactory(
        session=session,
        resources=resources,
        tenant_settings=dict(context.tenant.settings or {}),
    )


ServicesDep = Annotated[ServiceFactory, Depends(get_services)]


async def get_unscoped_services(
    session: UnscopedSessionDep, resources: ResourcesDep
) -> ServiceFactory:
    """Assemble services with no tenant context.

    Only the identity services are usable here: a tenant-owned repository
    raises ``TenantContextMissingError`` rather than running unscoped, and RLS
    would return nothing even if one slipped through.
    """
    return ServiceFactory(session=session, resources=resources)


UnscopedServicesDep = Annotated[ServiceFactory, Depends(get_unscoped_services)]


async def get_auth_service(
    session: UnscopedSessionDep,
    resources: ResourcesDep,
    services: UnscopedServicesDep,
) -> AuthService:
    """The authentication service.

    Deliberately built on the unscoped session: login and refresh have to run
    before any workspace is selected.
    """
    return AuthService(
        session=session,
        users=services.users,
        tenants=services.tenants,
        memberships=services.memberships,
        sessions=services.refresh_sessions,
        permissions=services.effective_permissions,
        password_hasher=resources.password_hasher,
        jwt_service=resources.jwt_service,
        audit=services.audit,
        settings=resources.settings,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user_services(
    principal: PrincipalDep, services: UnscopedServicesDep
) -> ServiceFactory:
    """Identity services for an authenticated but workspace-less caller."""
    return services


CurrentUserServicesDep = Annotated[ServiceFactory, Depends(get_current_user_services)]

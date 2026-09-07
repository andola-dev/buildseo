"""Tenant context dependencies.

This module is the gate described in the architecture: nothing reaches a
tenant-owned repository without passing through it.

    access token -> user -> ACTIVE membership -> tenant context -> permissions

The workspace can be named by the token's ``tid`` claim or by an ``X-Tenant-ID``
header (useful for a client that holds one token and switches workspace per
request). Both are treated identically: as a *request*, validated against
``tenant_memberships`` before anything else happens. A forged or stale value
buys nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.db import UnscopedSessionDep
from app.config.logging import get_logger
from app.core.context import set_tenant_id
from app.core.enums import TenantStatus
from app.core.exceptions import TenantAccessError, TenantContextMissingError
from app.db.session import TenantAwareSession
from app.models.tenants import Tenant, TenantMembership
from app.repositories.rbac import EffectivePermissionRepository
from app.repositories.tenants import MembershipRepository, TenantRepositoryGlobal

logger = get_logger(__name__)


@dataclass(slots=True)
class TenantContext:
    """A validated workspace context for this request."""

    tenant: Tenant
    membership: TenantMembership
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def tenant_id(self) -> UUID:
        return self.tenant.id

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


async def get_tenant_context(
    principal: PrincipalDep,
    session: UnscopedSessionDep,
    x_tenant_id: Annotated[
        UUID | None,
        Header(
            alias="X-Tenant-ID",
            description=(
                "Workspace to act in for this request. Overrides the token's claim. "
                "Membership is validated server-side."
            ),
        ),
    ] = None,
) -> TenantContext:
    """Validate membership, then establish the PostgreSQL tenant context.

    The ``set_tenant_context`` call is the handshake that switches RLS on for
    this request: until it happens, ``app.current_tenant_id`` is NULL and every
    tenant-owned table returns nothing.
    """
    requested = x_tenant_id or principal.claimed_tenant_id
    if requested is None:
        raise TenantContextMissingError(
            "Select a workspace with POST /api/v1/auth/select-tenant, "
            "or send an X-Tenant-ID header"
        )

    memberships = MembershipRepository(session)
    membership = await memberships.get_active_for_user_and_tenant(
        user_id=principal.user_id, tenant_id=requested
    )
    if membership is None:
        # Uniform refusal whether the workspace does not exist or the caller
        # simply has no membership in it, so ids cannot be probed.
        logger.warning(
            "tenant access denied",
            extra={
                "user_id": str(principal.user_id),
                "requested_tenant_id": str(requested),
            },
        )
        raise TenantAccessError()

    tenant = await TenantRepositoryGlobal(session).get_by_id(requested)
    if tenant is None or tenant.status != TenantStatus.ACTIVE.value:
        raise TenantAccessError(
            "This workspace is not active",
            code="TENANT_INACTIVE",
            details={"status": tenant.status if tenant else "MISSING"},
        )

    # From here on, PostgreSQL itself confines this transaction to one tenant.
    await session.set_tenant_context(tenant_id=tenant.id, user_id=principal.user_id)
    set_tenant_id(tenant.id)

    permissions = await EffectivePermissionRepository(session).codes_for_user_in_tenant(
        user_id=principal.user_id, tenant_id=tenant.id
    )
    return TenantContext(tenant=tenant, membership=membership, permissions=permissions)


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


async def get_tenant_session(
    session: UnscopedSessionDep,
    context: TenantContextDep,
) -> TenantAwareSession:
    """The request's session, with tenant context already applied.

    Depending on this (rather than on the unscoped session) is what makes a
    tenant-scoped repository usable: ``require_tenant_id()`` succeeds only
    because ``get_tenant_context`` ran first and bound the session.
    """
    assert session.tenant_id == context.tenant_id
    return session


TenantSessionDep = Annotated[TenantAwareSession, Depends(get_tenant_session)]

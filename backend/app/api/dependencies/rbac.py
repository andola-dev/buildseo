"""Authorisation dependencies.

The only authorisation primitive in the codebase. Routes declare a permission
code and this resolves it against the caller's effective permission set:

    @router.post("", dependencies=[Depends(require_permission(Perm.PUBLISHER_CREATE))])

There is no equivalent that checks a role name, deliberately — roles exist for
humans, permissions for code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.api.dependencies.tenant import TenantContext, TenantContextDep
from app.config.logging import get_logger
from app.core.exceptions import AuthorizationError
from app.rbac.catalog import Perm

logger = get_logger(__name__)

PermissionChecker = Callable[[TenantContext], Awaitable[TenantContext]]


def _deny(context: TenantContext, required: str) -> None:
    logger.warning(
        "permission denied",
        extra={
            "user_id": str(context.membership.user_id),
            "tenant_id": str(context.tenant_id),
            "required_permission": required,
        },
    )
    raise AuthorizationError.for_permission(required)


def require_permission(permission: Perm | str) -> PermissionChecker:
    """Require one permission.

    Returns a dependency so it can be used either in ``dependencies=[...]`` or
    as a parameter when the handler also wants the context.
    """
    code = str(permission)

    async def dependency(context: TenantContextDep) -> TenantContext:
        if not context.has_permission(code):
            _deny(context, code)
        return context

    dependency.__name__ = f"require_{code.replace('.', '_')}"
    dependency.__doc__ = f"Requires the '{code}' permission."
    return dependency


def require_all_permissions(*permissions: Perm | str) -> PermissionChecker:
    """Require every listed permission."""
    codes = [str(permission) for permission in permissions]

    async def dependency(context: TenantContextDep) -> TenantContext:
        missing = [code for code in codes if not context.has_permission(code)]
        if missing:
            _deny(context, ", ".join(missing))
        return context

    dependency.__doc__ = f"Requires all of: {', '.join(codes)}."
    return dependency


def require_any_permission(*permissions: Perm | str) -> PermissionChecker:
    """Require at least one of the listed permissions."""
    codes = [str(permission) for permission in permissions]

    async def dependency(context: TenantContextDep) -> TenantContext:
        if not any(context.has_permission(code) for code in codes):
            _deny(context, " or ".join(codes))
        return context

    dependency.__doc__ = f"Requires any of: {', '.join(codes)}."
    return dependency


def require_owner() -> PermissionChecker:
    """Require workspace ownership.

    The one guard that is not purely permission-based, because ownership is a
    property of the *membership* rather than a grantable capability: an Admin
    holds every permission an Owner does except the two ownership-level ones,
    and ownership transfer must additionally be performed by an actual owner.
    """

    async def dependency(context: TenantContextDep) -> TenantContext:
        if not context.membership.is_owner:
            _deny(context, "workspace ownership")
        return context

    dependency.__doc__ = "Requires the caller to be an owner of the workspace."
    return dependency

"""Permission-based authorisation.

The rule this package exists to enforce: authorisation is *always* a permission
check. Nowhere in the codebase does control flow branch on a role name.
"""

from app.rbac.catalog import (
    DEFAULT_ROLE_DEFINITIONS,
    PERMISSION_CATALOG,
    Perm,
    PermissionSpec,
    RoleDefinition,
    permissions_for_role,
)

__all__ = [
    "DEFAULT_ROLE_DEFINITIONS",
    "PERMISSION_CATALOG",
    "Perm",
    "PermissionSpec",
    "RoleDefinition",
    "permissions_for_role",
]

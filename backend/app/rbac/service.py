"""Role administration and permission resolution."""

from __future__ import annotations

from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.exceptions import (
    BusinessRuleError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.rbac import Permission, Role
from app.rbac.catalog import ALL_PERMISSIONS
from app.repositories.rbac import (
    EffectivePermissionRepository,
    MembershipRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)

logger = get_logger(__name__)


class RbacService:
    """Custom role CRUD and effective-permission lookup.

    System roles are read-only through the API. A workspace that could strip
    permissions from its own Owner role could lock itself out entirely, so
    ``is_system`` roles reject edits and deletion — a tenant that wants
    different permissions creates a custom role instead.
    """

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        roles: RoleRepository,
        permissions: PermissionRepository,
        role_permissions: RolePermissionRepository,
        membership_roles: MembershipRoleRepository,
        effective: EffectivePermissionRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._roles = roles
        self._permissions = permissions
        self._role_permissions = role_permissions
        self._membership_roles = membership_roles
        self._effective = effective
        self._audit = audit

    # -------------------------------------------------------- permissions --

    async def list_permissions(self) -> list[Permission]:
        return await self._permissions.list_all()

    async def effective_permissions(self, *, user_id: UUID, tenant_id: UUID) -> frozenset[str]:
        """The union of permissions across a member's roles.

        Resolved from the database on every request rather than cached in the
        access token, so revoking a role takes effect immediately instead of
        at token expiry.
        """
        return await self._effective.codes_for_user_in_tenant(user_id=user_id, tenant_id=tenant_id)

    async def _resolve_permission_ids(self, codes: list[str]) -> list[UUID]:
        """Map permission codes to ids, rejecting anything unrecognised.

        Unknown codes are an error rather than a silent no-op: a role that
        looks like it grants ``publisher.publish`` but grants nothing is worse
        than a rejected request.
        """
        requested = list(dict.fromkeys(codes))
        known_codes = {perm.value for perm in ALL_PERMISSIONS}
        unknown = [code for code in requested if code not in known_codes]
        if unknown:
            raise ValidationError(
                "Unknown permission codes",
                code="UNKNOWN_PERMISSION",
                details={"unknown": sorted(unknown)},
            )
        rows = await self._permissions.get_by_codes(requested)
        if len(rows) != len(requested):
            found = {row.code for row in rows}
            raise BusinessRuleError(
                "The permission catalog is incomplete; run the seed script",
                code="PERMISSION_CATALOG_INCOMPLETE",
                details={"missing": sorted(set(requested) - found)},
            )
        return [row.id for row in rows]

    # --------------------------------------------------------------- roles --

    async def list_roles(
        self, *, page: PageParams, sort: SortParams | None, is_system: bool | None = None
    ) -> Page[Role]:
        return await self._roles.list_page_with_permissions(
            page=page, sort=sort, is_system=is_system
        )

    async def get_role(self, role_id: UUID) -> Role:
        role = await self._roles.get_with_permissions(role_id)
        if role is None:
            raise ResourceNotFoundError.for_resource("role", role_id)
        return role

    async def permission_codes(self, role_id: UUID) -> list[str]:
        return await self._role_permissions.list_permission_codes_for_role(role_id)

    async def create_role(
        self, *, slug: str, name: str, description: str | None, permissions: list[str]
    ) -> Role:
        if await self._roles.get_by_slug(slug) is not None:
            raise DuplicateResourceError(
                f"A role with the handle '{slug}' already exists in this workspace",
                code="ROLE_SLUG_TAKEN",
                details={"slug": slug},
            )
        permission_ids = await self._resolve_permission_ids(permissions)

        role = self._roles.new(slug=slug, name=name, description=description, is_system=False)
        await self._session.flush()
        await self._role_permissions.replace_for_role(role.id, permission_ids)

        await self._audit.record(
            AuditAction.ROLE_CREATED,
            resource_type="role",
            resource_id=role.id,
            metadata={"slug": slug, "name": name, "permission_count": len(permission_ids)},
        )
        return role

    async def update_role(
        self,
        *,
        role_id: UUID,
        name: str | None,
        description: str | None,
        permissions: list[str] | None,
    ) -> Role:
        role = await self._roles.get(role_id)
        if role is None:
            raise ResourceNotFoundError.for_resource("role", role_id)
        if role.is_system:
            raise BusinessRuleError(
                "System roles cannot be modified. Create a custom role instead.",
                code="SYSTEM_ROLE_IMMUTABLE",
                details={"slug": role.slug},
            )

        changed: list[str] = []
        if name is not None and name != role.name:
            role.name = name
            changed.append("name")
        if description is not None and description != role.description:
            role.description = description
            changed.append("description")

        permission_count = 0
        if permissions is not None:
            permission_ids = await self._resolve_permission_ids(permissions)
            await self._role_permissions.replace_for_role(role.id, permission_ids)
            permission_count = len(permission_ids)
            changed.append("permissions")

        await self._session.flush()
        await self._audit.record(
            AuditAction.ROLE_UPDATED,
            resource_type="role",
            resource_id=role.id,
            metadata={
                "slug": role.slug,
                "name": role.name,
                "changed_fields": changed,
                "permission_count": permission_count,
            },
        )
        return role

    async def delete_role(self, role_id: UUID) -> None:
        role = await self._roles.get(role_id)
        if role is None:
            raise ResourceNotFoundError.for_resource("role", role_id)
        if role.is_system:
            raise BusinessRuleError(
                "System roles cannot be deleted",
                code="SYSTEM_ROLE_IMMUTABLE",
                details={"slug": role.slug},
            )

        assigned = await self._membership_roles.count_for_role(role_id)
        if assigned:
            # Deleting it would silently strip permissions from those members.
            raise BusinessRuleError(
                f"This role is still assigned to {assigned} member(s)",
                code="ROLE_IN_USE",
                details={"assigned_members": assigned},
            )

        slug, name = role.slug, role.name
        await self._session.delete(role)
        await self._session.flush()
        await self._audit.record(
            AuditAction.ROLE_DELETED,
            resource_type="role",
            resource_id=role_id,
            metadata={"slug": slug, "name": name},
        )

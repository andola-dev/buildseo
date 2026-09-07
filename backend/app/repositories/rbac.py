"""Permission, role and assignment data access."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.pagination import Page, PageParams, SortParams
from app.models.rbac import MembershipRole, Permission, Role, RolePermission
from app.models.tenants import TenantMembership
from app.repositories.base import BaseRepository, TenantRepository


class PermissionRepository(BaseRepository[Permission]):
    """The global permission catalog. Read-only outside seeding."""

    model = Permission
    sortable_fields = frozenset({"code", "resource", "action"})
    default_sort = "code"

    async def list_all(self) -> list[Permission]:
        result = await self.session.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return list(result.scalars().all())

    async def get_by_codes(self, codes: Sequence[str]) -> list[Permission]:
        if not codes:
            return []
        result = await self.session.execute(
            select(Permission).where(Permission.code.in_(list(codes)))
        )
        return list(result.scalars().all())

    async def map_by_code(self) -> dict[str, Permission]:
        return {permission.code: permission for permission in await self.list_all()}


class RoleRepository(TenantRepository[Role]):
    """Per-tenant roles."""

    model = Role
    sortable_fields = frozenset({"created_at", "updated_at", "name", "slug"})
    default_sort = "name"

    async def get_by_slug(self, slug: str) -> Role | None:
        result = await self.session.execute(self._select().where(Role.slug == slug))
        return result.scalar_one_or_none()

    async def get_with_permissions(self, role_id: UUID) -> Role | None:
        result = await self.session.execute(
            self._select()
            .where(Role.id == role_id)
            .options(selectinload(Role.permission_links).selectinload(RolePermission.permission))
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        result = await self.session.execute(self._select().order_by(Role.name))
        return list(result.scalars().all())

    async def list_page_with_permissions(
        self, *, page: PageParams, sort: SortParams | None = None, is_system: bool | None = None
    ) -> Page[Role]:
        statement = self._select().options(
            selectinload(Role.permission_links).selectinload(RolePermission.permission)
        )
        if is_system is not None:
            statement = statement.where(Role.is_system.is_(is_system))
        return await self._paginate(statement, page=page, sort=sort)

    async def get_by_slugs(self, slugs: Sequence[str]) -> list[Role]:
        if not slugs:
            return []
        result = await self.session.execute(self._select().where(Role.slug.in_(list(slugs))))
        return list(result.scalars().all())


class RolePermissionRepository(TenantRepository[RolePermission]):
    """Role-to-permission grants."""

    model = RolePermission
    sortable_fields = frozenset({"id"})
    default_sort = "id"

    async def replace_for_role(self, role_id: UUID, permission_ids: Sequence[UUID]) -> None:
        """Set a role's grants to exactly ``permission_ids``.

        Delete-then-insert rather than a diff: the whole operation runs in the
        request's transaction, so there is no window in which the role has
        partial permissions, and the code stays obviously correct.
        """
        await self.session.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == self.tenant_id,
                RolePermission.role_id == role_id,
            )
        )
        for permission_id in dict.fromkeys(permission_ids):
            self.new(role_id=role_id, permission_id=permission_id)
        await self.session.flush()

    async def list_permission_codes_for_role(self, role_id: UUID) -> list[str]:
        result = await self.session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.tenant_id == self.tenant_id,
                RolePermission.role_id == role_id,
            )
            .order_by(Permission.code)
        )
        return list(result.scalars().all())


class MembershipRoleRepository(TenantRepository[MembershipRole]):
    """Role assignments on a membership."""

    model = MembershipRole
    sortable_fields = frozenset({"id"})
    default_sort = "id"

    async def replace_for_membership(self, membership_id: UUID, role_ids: Sequence[UUID]) -> None:
        await self.session.execute(
            delete(MembershipRole).where(
                MembershipRole.tenant_id == self.tenant_id,
                MembershipRole.membership_id == membership_id,
            )
        )
        for role_id in dict.fromkeys(role_ids):
            self.new(membership_id=membership_id, role_id=role_id)
        await self.session.flush()

    async def list_roles_for_membership(self, membership_id: UUID) -> list[Role]:
        result = await self.session.execute(
            select(Role)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == self.tenant_id,
                MembershipRole.membership_id == membership_id,
            )
            .order_by(Role.name)
        )
        return list(result.scalars().all())

    async def count_for_role(self, role_id: UUID) -> int:
        """How many members hold a role — checked before deleting it."""
        return await self.count([MembershipRole.role_id == role_id])


class EffectivePermissionRepository(BaseRepository[Permission]):
    """Resolves a member's effective permission set.

    One query walks membership → membership_roles → role_permissions →
    permissions and returns the union of codes. Loading it per request (rather
    than caching it in the access token) means a revoked role takes effect on
    the caller's very next request instead of when their token expires.
    """

    model = Permission

    async def codes_for_user_in_tenant(self, *, user_id: UUID, tenant_id: UUID) -> frozenset[str]:
        statement = (
            select(Permission.code)
            .distinct()
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
            .join(TenantMembership, TenantMembership.id == MembershipRole.membership_id)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                # An ACTIVE membership is the only one that grants anything: a
                # SUSPENDED member keeps their role rows but no permissions.
                TenantMembership.status == "ACTIVE",
                MembershipRole.tenant_id == tenant_id,
                RolePermission.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(statement)
        return frozenset(result.scalars().all())

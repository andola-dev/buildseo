"""Tenant and membership data access."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.enums import MembershipStatus, TenantStatus
from app.core.pagination import Page, PageParams, SortParams
from app.models.tenants import Tenant, TenantMembership
from app.repositories.base import BaseRepository


class TenantRepositoryGlobal(BaseRepository[Tenant]):
    """Access to ``tenants``, a global table.

    Named ``...Global`` to keep it clearly distinct from
    :class:`app.repositories.base.TenantRepository`, which is the base class for
    tenant-*owned* tables. Visibility here is enforced by joining
    ``tenant_memberships``: a caller only ever sees workspaces they belong to.
    """

    model = Tenant
    sortable_fields = frozenset({"created_at", "updated_at", "name", "slug"})
    default_sort = "created_at"

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(Tenant).where(Tenant.slug == slug)
        )
        return int(result.scalar_one()) > 0

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        page: PageParams,
        sort: SortParams | None = None,
        only_active_membership: bool = True,
    ) -> Page[Tenant]:
        """Workspaces this user may enter."""
        statement = (
            select(Tenant)
            .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
            .where(TenantMembership.user_id == user_id)
        )
        if only_active_membership:
            statement = statement.where(
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                Tenant.status == TenantStatus.ACTIVE.value,
            )
        return await self._paginate(statement, page=page, sort=sort)


class MembershipRepository(BaseRepository[TenantMembership]):
    """Access to ``tenant_memberships``.

    This repository is intentionally *not* a ``TenantRepository``: membership
    lookup is what establishes the tenant context in the first place, so it has
    to run before one exists. The database still protects the table — the RLS
    policy allows a row when it matches the current tenant **or** the current
    user — and every method here filters explicitly by user, tenant, or both.
    """

    model = TenantMembership
    sortable_fields = frozenset({"created_at", "updated_at", "status"})
    default_sort = "created_at"

    async def get_for_user_and_tenant(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> TenantMembership | None:
        """The single row that authorises (or refuses) tenant access."""
        result = await self.session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_user_and_tenant(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> TenantMembership | None:
        """Only an ACTIVE membership grants access."""
        result = await self.session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[TenantMembership]:
        result = await self.session.execute(
            select(TenantMembership)
            .where(TenantMembership.user_id == user_id)
            .order_by(TenantMembership.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_id_in_tenant(
        self, membership_id: UUID, tenant_id: UUID
    ) -> TenantMembership | None:
        result = await self.session.execute(
            select(TenantMembership)
            .where(
                TenantMembership.id == membership_id,
                TenantMembership.tenant_id == tenant_id,
            )
            .options(selectinload(TenantMembership.role_links))
        )
        return result.scalar_one_or_none()

    async def list_page_for_tenant(
        self,
        tenant_id: UUID,
        *,
        page: PageParams,
        sort: SortParams | None = None,
        status: str | None = None,
    ) -> Page[TenantMembership]:
        statement = select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
        if status:
            statement = statement.where(TenantMembership.status == status)
        return await self._paginate(statement, page=page, sort=sort)

    async def count_owners(self, tenant_id: UUID) -> int:
        """Used to refuse removing or demoting the last owner."""
        result = await self.session.execute(
            select(func.count())
            .select_from(TenantMembership)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.is_owner.is_(True),
                TenantMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        return int(result.scalar_one())

"""User data access.

``users`` is a global table, so this repository is *not* tenant-scoped. That
makes it the one place where tenant scoping must be explicit: listing users
always goes through :meth:`UserRepository.list_for_tenant`, which joins
``tenant_memberships``, so a tenant can only ever see its own members.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.core.pagination import Page, PageParams, SortParams
from app.models.tenants import TenantMembership
from app.models.users import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    sortable_fields = frozenset({"created_at", "updated_at", "email", "last_login_at"})
    default_sort = "created_at"

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Look up by email.

        The comparison is case-insensitive because ``users.email`` is CITEXT,
        so this cannot be bypassed by varying capitalisation.
        """
        result = await self.session.execute(select(User).where(User.email == email.strip()))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.email == email.strip())
        )
        return int(result.scalar_one()) > 0

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        page: PageParams,
        sort: SortParams | None = None,
        search: str | None = None,
        membership_status: str | None = None,
    ) -> Page[User]:
        """Members of one tenant.

        The membership join is the tenant filter. ``users`` carries no
        ``tenant_id``, so this join — not an RLS policy — is what confines the
        result to the caller's workspace.
        """
        statement = (
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(TenantMembership.tenant_id == tenant_id)
        )
        if membership_status:
            statement = statement.where(TenantMembership.status == membership_status)
        if search:
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    User.email.ilike(term),
                    User.first_name.ilike(term),
                    User.last_name.ilike(term),
                )
            )
        return await self._paginate(statement, page=page, sort=sort)

    async def get_tenant_member(self, tenant_id: UUID, user_id: UUID) -> User | None:
        """Fetch a user only if they belong to ``tenant_id``."""
        statement = (
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(TenantMembership.tenant_id == tenant_id, User.id == user_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_many(self, user_ids: Sequence[UUID]) -> list[User]:
        if not user_ids:
            return []
        result = await self.session.execute(select(User).where(User.id.in_(list(user_ids))))
        return list(result.scalars().all())

    def build_filters(self, *, is_active: bool | None = None) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if is_active is not None:
            filters.append(User.is_active.is_(is_active))
        return filters

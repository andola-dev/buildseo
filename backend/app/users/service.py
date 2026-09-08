"""User profile and workspace-directory queries."""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.users import User
from app.repositories.tenants import MembershipRepository, TenantRepositoryGlobal
from app.repositories.users import UserRepository
from app.schemas.users import TenantMembershipSummary


class UserService:
    """Reads and updates users.

    ``users`` is a global table with no RLS, so every listing here goes through
    a membership join: a caller can only ever see the members of the workspace
    they are acting in.
    """

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        users: UserRepository,
        memberships: MembershipRepository,
        tenants: TenantRepositoryGlobal,
    ) -> None:
        self._session = session
        self._users = users
        self._memberships = memberships
        self._tenants = tenants

    async def list_tenant_members(
        self,
        *,
        tenant_id: UUID,
        page: PageParams,
        sort: SortParams | None,
        search: str | None = None,
        membership_status: str | None = None,
    ) -> Page[User]:
        return await self._users.list_for_tenant(
            tenant_id,
            page=page,
            sort=sort,
            search=search,
            membership_status=membership_status,
        )

    async def get_tenant_member(self, *, tenant_id: UUID, user_id: UUID) -> User:
        """Fetch a member of the active workspace.

        A user who exists but is not a member surfaces as 404, not 403, so the
        endpoint cannot be used to probe the platform's user base.
        """
        user = await self._users.get_tenant_member(tenant_id, user_id)
        if user is None:
            raise ResourceNotFoundError.for_resource("user", user_id)
        return user

    async def update_profile(
        self, *, user: User, first_name: str | None, last_name: str | None
    ) -> User:
        if first_name is not None:
            user.first_name = first_name or None
        if last_name is not None:
            user.last_name = last_name or None
        await self._session.flush()
        return user

    async def membership_summaries(
        self, user_id: UUID, *, roles_by_membership: dict[UUID, list[str]] | None = None
    ) -> list[TenantMembershipSummary]:
        """The workspaces a user belongs to, for ``GET /me``."""
        memberships = await self._memberships.list_for_user(user_id)
        if not memberships:
            return []

        tenants = {}
        for membership in memberships:
            tenant = await self._tenants.get_by_id(membership.tenant_id)
            if tenant is not None:
                tenants[membership.tenant_id] = tenant

        summaries: list[TenantMembershipSummary] = []
        for membership in memberships:
            tenant = tenants.get(membership.tenant_id)
            if tenant is None:
                continue
            summaries.append(
                TenantMembershipSummary(
                    tenant_id=tenant.id,
                    tenant_name=tenant.name,
                    tenant_slug=tenant.slug,
                    status=membership.status,
                    is_owner=membership.is_owner,
                    roles=(roles_by_membership or {}).get(membership.id, []),
                )
            )
        return summaries

"""Tenant provisioning and membership management.

Creating a workspace is the one flow that has to bootstrap its own tenant
context: the caller has no membership in a workspace that does not exist yet.
The order is therefore fixed and matters —

1. insert the ``tenants`` row (a global table, no RLS),
2. set the session's tenant context to the new id,
3. insert the tenant-owned rows (roles, grants, the owner membership).

Step 2 sits between the two because every insert after it is checked by an RLS
``WITH CHECK`` predicate against ``app.current_tenant_id``.
"""

from __future__ import annotations

import re
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import SENSITIVE_KEY_PARTS, get_logger
from app.core.enums import MembershipStatus, SystemRoleSlug, TenantStatus
from app.core.exceptions import (
    BusinessRuleError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.rbac import Role
from app.models.tenants import Tenant, TenantMembership
from app.models.users import User
from app.rbac.catalog import DEFAULT_ROLE_DEFINITIONS
from app.repositories.rbac import (
    MembershipRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.repositories.tenants import MembershipRepository, TenantRepositoryGlobal
from app.repositories.users import UserRepository

logger = get_logger(__name__)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
MAX_SLUG_LENGTH = 64


def slugify(value: str) -> str:
    """Derive a URL-safe workspace handle from a name."""
    lowered = _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")
    trimmed = lowered[:MAX_SLUG_LENGTH].strip("-")
    if len(trimmed) < 3:
        # Matches ``ck_tenants_slug_format``; the caller supplies an explicit
        # slug when the name does not yield a usable one.
        raise ValidationError(
            "Could not derive a workspace handle from that name; supply 'slug' explicitly",
            code="INVALID_SLUG",
        )
    return trimmed


class TenantService:
    """Workspace creation, settings and membership administration."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        tenants: TenantRepositoryGlobal,
        memberships: MembershipRepository,
        users: UserRepository,
        roles: RoleRepository,
        role_permissions: RolePermissionRepository,
        membership_roles: MembershipRoleRepository,
        permissions: PermissionRepository,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._tenants = tenants
        self._memberships = memberships
        self._users = users
        self._roles = roles
        self._role_permissions = role_permissions
        self._membership_roles = membership_roles
        self._permissions = permissions
        self._audit = audit

    # ----------------------------------------------------------- provision --

    async def create_tenant(
        self, *, name: str, slug: str | None, owner: User
    ) -> tuple[Tenant, TenantMembership]:
        """Create a workspace, seed its roles, and make ``owner`` its owner."""
        handle = (slug or slugify(name)).lower()
        if await self._tenants.slug_exists(handle):
            raise DuplicateResourceError(
                f"The workspace handle '{handle}' is already taken",
                code="TENANT_SLUG_TAKEN",
                details={"slug": handle},
            )

        tenant = Tenant(
            name=name.strip(),
            slug=handle,
            status=TenantStatus.ACTIVE.value,
            created_by_user_id=owner.id,
            settings={},
        )
        self._session.add(tenant)
        await self._session.flush()

        # Everything below this line writes tenant-owned rows, so the RLS
        # context must be established first or the inserts are refused.
        await self._session.set_tenant_context(tenant_id=tenant.id, user_id=owner.id)

        roles = await self.seed_system_roles(tenant.id)
        membership = await self._create_membership(
            tenant_id=tenant.id,
            user=owner,
            role_slugs=[SystemRoleSlug.OWNER.value],
            status=MembershipStatus.ACTIVE,
            is_owner=True,
            available_roles=roles,
        )

        await self._audit.record(
            AuditAction.TENANT_CREATED,
            resource_type="tenant",
            resource_id=tenant.id,
            user_id=owner.id,
            metadata={"name": tenant.name, "slug": tenant.slug},
        )
        logger.info(
            "workspace created",
            extra={"tenant_id": str(tenant.id), "tenant_slug": tenant.slug},
        )
        return tenant, membership

    async def seed_system_roles(self, tenant_id: UUID) -> dict[str, Role]:
        """Create this workspace's copy of the five default roles.

        Roles are per tenant rather than global so a workspace can edit or
        extend its own without affecting anyone else. Idempotent: an existing
        role of the same slug is reused, so re-running the seed is safe.
        """
        catalog = await self._permissions.map_by_code()
        missing_from_catalog: set[str] = set()
        existing = {role.slug: role for role in await self._roles.list_all()}
        result: dict[str, Role] = {}

        for definition in DEFAULT_ROLE_DEFINITIONS:
            role = existing.get(definition.slug.value)
            if role is None:
                role = self._roles.new(
                    slug=definition.slug.value,
                    name=definition.name,
                    description=definition.description,
                    is_system=True,
                )
                await self._session.flush()

            permission_ids = []
            for perm in sorted(definition.permissions):
                entry = catalog.get(perm.value)
                if entry is None:
                    missing_from_catalog.add(perm.value)
                    continue
                permission_ids.append(entry.id)
            await self._role_permissions.replace_for_role(role.id, permission_ids)
            result[definition.slug.value] = role

        if missing_from_catalog:
            # The permission catalog is seeded by scripts/seed.py before any
            # workspace exists; a gap here means that step was skipped.
            raise BusinessRuleError(
                "The permission catalog is incomplete; run the seed script",
                code="PERMISSION_CATALOG_INCOMPLETE",
                details={"missing": sorted(missing_from_catalog)},
            )
        return result

    # ---------------------------------------------------------- membership --

    async def _create_membership(
        self,
        *,
        tenant_id: UUID,
        user: User,
        role_slugs: list[str],
        status: MembershipStatus,
        is_owner: bool,
        available_roles: dict[str, Role] | None = None,
    ) -> TenantMembership:
        roles = available_roles or {role.slug: role for role in await self._roles.list_all()}
        unknown = [slug for slug in role_slugs if slug not in roles]
        if unknown:
            raise ResourceNotFoundError(
                "One or more roles do not exist in this workspace",
                code="ROLE_NOT_FOUND",
                details={"unknown_roles": unknown},
            )

        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            status=status.value,
            is_owner=is_owner,
        )
        self._session.add(membership)
        await self._session.flush()

        await self._membership_roles.replace_for_membership(
            membership.id, [roles[slug].id for slug in role_slugs]
        )
        return membership

    async def add_member(
        self,
        *,
        tenant_id: UUID,
        email: str | None,
        user_id: UUID | None,
        role_slugs: list[str],
        status: MembershipStatus,
    ) -> TenantMembership:
        """Add an existing account to this workspace.

        There is no email delivery in this phase, so this adds an account that
        already exists rather than sending an invitation.
        """
        if not email and not user_id:
            raise ValidationError(
                "Provide either 'email' or 'user_id'", code="MEMBER_IDENTIFIER_REQUIRED"
            )

        user = (
            await self._users.get_by_id(user_id)
            if user_id
            else await self._users.get_by_email(email or "")
        )
        if user is None:
            # Deliberately does not distinguish "no such account" from
            # "account exists but you may not see it": an operator adding a
            # member must not be able to probe the platform's user base.
            raise ResourceNotFoundError(
                "No account matches that identifier. The person must register first.",
                code="USER_NOT_FOUND",
            )
        if not user.is_active:
            raise BusinessRuleError("That account is deactivated", code="USER_INACTIVE")

        existing = await self._memberships.get_for_user_and_tenant(
            user_id=user.id, tenant_id=tenant_id
        )
        if existing is not None:
            raise DuplicateResourceError(
                "That account is already a member of this workspace",
                code="MEMBERSHIP_EXISTS",
            )

        membership = await self._create_membership(
            tenant_id=tenant_id,
            user=user,
            role_slugs=role_slugs,
            status=status,
            is_owner=False,
        )
        await self._audit.record(
            AuditAction.MEMBER_ADDED,
            resource_type="membership",
            resource_id=membership.id,
            metadata={
                "user_id": str(user.id),
                "email": user.email,
                "role_slugs": role_slugs,
                "status": status.value,
            },
        )
        return membership

    async def update_member(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        status: MembershipStatus | None,
        role_slugs: list[str] | None,
        is_owner: bool | None,
    ) -> TenantMembership:
        """Change a member's status, roles or ownership."""
        membership = await self._memberships.get_by_id_in_tenant(membership_id, tenant_id)
        if membership is None:
            raise ResourceNotFoundError.for_resource("membership", membership_id)

        changed: list[str] = []

        # Guard the last owner *before* applying anything, so a rejected change
        # leaves nothing half-applied.
        losing_ownership = (is_owner is False and membership.is_owner) or (
            status is not None and status is not MembershipStatus.ACTIVE and membership.is_owner
        )
        if losing_ownership and await self._memberships.count_owners(tenant_id) <= 1:
            raise BusinessRuleError(
                "This workspace must keep at least one active owner",
                code="LAST_OWNER_PROTECTED",
            )

        if status is not None and status.value != membership.status:
            membership.status = status.value
            changed.append("status")
        if is_owner is not None and is_owner != membership.is_owner:
            membership.is_owner = is_owner
            changed.append("is_owner")
        if role_slugs is not None:
            roles = {role.slug: role for role in await self._roles.list_all()}
            unknown = [slug for slug in role_slugs if slug not in roles]
            if unknown:
                raise ResourceNotFoundError(
                    "One or more roles do not exist in this workspace",
                    code="ROLE_NOT_FOUND",
                    details={"unknown_roles": unknown},
                )
            await self._membership_roles.replace_for_membership(
                membership.id, [roles[slug].id for slug in role_slugs]
            )
            changed.append("roles")

        await self._session.flush()
        await self._audit.record(
            AuditAction.MEMBER_UPDATED,
            resource_type="membership",
            resource_id=membership.id,
            metadata={
                "user_id": str(membership.user_id),
                "changed_fields": changed,
                "status": membership.status,
                "is_owner": membership.is_owner,
                "role_slugs": role_slugs or [],
            },
        )
        return membership

    async def remove_member(self, *, tenant_id: UUID, membership_id: UUID) -> None:
        """Remove a member, protecting the last owner."""
        membership = await self._memberships.get_by_id_in_tenant(membership_id, tenant_id)
        if membership is None:
            raise ResourceNotFoundError.for_resource("membership", membership_id)
        if membership.is_owner and await self._memberships.count_owners(tenant_id) <= 1:
            raise BusinessRuleError(
                "This workspace must keep at least one active owner",
                code="LAST_OWNER_PROTECTED",
            )

        user = await self._users.get_by_id(membership.user_id)
        await self._session.delete(membership)
        await self._session.flush()
        await self._audit.record(
            AuditAction.MEMBER_REMOVED,
            resource_type="membership",
            resource_id=membership_id,
            metadata={
                "user_id": str(membership.user_id),
                "email": user.email if user else None,
            },
        )

    async def list_members(
        self, *, tenant_id: UUID, page: PageParams, sort: SortParams | None, status: str | None
    ) -> Page[TenantMembership]:
        return await self._memberships.list_page_for_tenant(
            tenant_id, page=page, sort=sort, status=status
        )

    async def roles_for_membership(self, membership_id: UUID) -> list[str]:
        roles = await self._membership_roles.list_roles_for_membership(membership_id)
        return [role.slug for role in roles]

    # ------------------------------------------------------------- settings --

    async def update_tenant(
        self,
        *,
        tenant: Tenant,
        name: str | None,
        status: TenantStatus | None,
        settings: dict[str, object] | None,
    ) -> Tenant:
        changed: list[str] = []
        if name is not None and name.strip() != tenant.name:
            tenant.name = name.strip()
            changed.append("name")
        if status is not None and status.value != tenant.status:
            tenant.status = status.value
            changed.append("status")
        if settings is not None:
            tenant.settings = _validate_settings(settings)
            changed.append("settings")

        await self._session.flush()
        await self._audit.record(
            AuditAction.TENANT_UPDATED,
            resource_type="tenant",
            resource_id=tenant.id,
            metadata={"changed_fields": changed, "status": tenant.status},
        )
        return tenant

    async def list_for_user(
        self, *, user_id: UUID, page: PageParams, sort: SortParams | None
    ) -> Page[Tenant]:
        return await self._tenants.list_for_user(user_id, page=page, sort=sort)


def _validate_settings(settings: dict[str, object]) -> dict[str, object]:
    """Refuse workspace settings that look like they carry a secret.

    ``tenants.settings`` is stored unencrypted and returned by the API, so a
    provider key placed there would bypass the credential encryption entirely.
    """
    offending = [
        key for key in settings if any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
    ]
    if offending:
        raise ValidationError(
            "Workspace settings must not contain secret-like keys; "
            "store provider credentials through /credentials instead",
            code="SECRET_IN_SETTINGS",
            details={"fields": sorted(offending)},
        )
    return settings

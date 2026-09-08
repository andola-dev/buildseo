"""Seeded roles and permissions, as they actually land in the database.

The permission catalog is the authorization vocabulary: ``require_permission``
compares against it, the ``/permissions`` endpoint publishes it, and every
seeded role is defined in terms of it. A gap between the Python catalog and the
database rows would mean a route that is nominally protected but effectively
unenforceable, so it is asserted end to end here rather than only in the unit
tests over the catalog module.
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bootstrap import AppResources
from app.core.enums import MembershipStatus, SystemRoleSlug
from app.db.session import TenantAwareSession
from app.models.rbac import Permission
from app.models.tenants import TenantMembership
from app.rbac.catalog import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE_DEFINITIONS,
    PERMISSION_CATALOG,
    Perm,
)
from app.repositories.rbac import (
    EffectivePermissionRepository,
    MembershipRoleRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.services.factory import ServiceFactory
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestPermissionCatalog:
    async def test_every_catalog_entry_exists_as_a_row(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        seeded_permissions: None,
    ) -> None:
        async with session_factory() as session:
            codes = set((await session.execute(select(Permission.code))).scalars().all())
        assert {spec.code for spec in PERMISSION_CATALOG} <= codes

    async def test_stored_resource_and_action_are_derived_from_the_code(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        seeded_permissions: None,
    ) -> None:
        """``resource``/``action`` are denormalised for grouping in the UI."""
        async with session_factory() as session:
            rows = (await session.execute(select(Permission))).scalars().all()
        for permission in rows:
            assert permission.code == f"{permission.resource}.{permission.action}"

    async def test_permission_codes_are_unique(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        seeded_permissions: None,
    ) -> None:
        async with session_factory() as session:
            total = (
                await session.execute(select(func.count()).select_from(Permission))
            ).scalar_one()
            distinct = (
                await session.execute(select(func.count(func.distinct(Permission.code))))
            ).scalar_one()
        assert total == distinct

    async def test_permissions_are_global_not_tenant_owned(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        seeded_permissions: None,
    ) -> None:
        """Documented in ARCHITECTURE §5.5: the vocabulary is shared, so the
        table carries no ``tenant_id`` and is deliberately outside RLS."""
        assert not hasattr(Permission, "tenant_id")


class TestSeededRoles:
    async def test_a_new_workspace_gets_all_five_system_roles(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = await RoleRepository(session).list_all()
            assert {role.slug for role in roles} == {slug.value for slug in SystemRoleSlug}
            assert all(role.is_system for role in roles)
        finally:
            await session.rollback()
            await session.close()

    async def test_roles_are_per_workspace_copies(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """So a tenant can edit its own roles without affecting anyone else."""
        slugs = {}
        for fixture in (tenant_a, tenant_b):
            session = session_factory()
            await session.set_tenant_context(tenant_id=fixture.tenant_id)
            try:
                roles = await RoleRepository(session).list_all()
                slugs[fixture.tenant_id] = {role.id for role in roles}
            finally:
                await session.rollback()
                await session.close()

        assert slugs[tenant_a.tenant_id].isdisjoint(slugs[tenant_b.tenant_id])

    async def test_each_role_holds_exactly_the_grants_the_catalog_defines(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = {role.slug: role for role in await RoleRepository(session).list_all()}
            grants = RolePermissionRepository(session)
            for definition in DEFAULT_ROLE_DEFINITIONS:
                stored = set(
                    await grants.list_permission_codes_for_role(roles[definition.slug.value].id)
                )
                assert stored == {
                    perm.value for perm in definition.permissions
                }, definition.slug.value
        finally:
            await session.rollback()
            await session.close()

    async def test_owner_holds_every_permission_and_admin_holds_all_but_ownership(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = {role.slug: role for role in await RoleRepository(session).list_all()}
            grants = RolePermissionRepository(session)
            owner = set(
                await grants.list_permission_codes_for_role(roles[SystemRoleSlug.OWNER.value].id)
            )
            admin = set(
                await grants.list_permission_codes_for_role(roles[SystemRoleSlug.ADMIN.value].id)
            )
            assert owner == {perm.value for perm in ALL_PERMISSIONS}
            assert owner - admin == {
                Perm.TENANT_DELETE.value,
                Perm.TENANT_TRANSFER_OWNERSHIP.value,
            }
        finally:
            await session.rollback()
            await session.close()

    async def test_the_privilege_ladder_nests_in_the_database(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Promoting a member must never take visibility away from them."""
        ladder = (
            SystemRoleSlug.VIEWER,
            SystemRoleSlug.SEO_SPECIALIST,
            SystemRoleSlug.SEO_MANAGER,
            SystemRoleSlug.ADMIN,
            SystemRoleSlug.OWNER,
        )
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = {role.slug: role for role in await RoleRepository(session).list_all()}
            grants = RolePermissionRepository(session)
            sets = [
                set(await grants.list_permission_codes_for_role(roles[slug.value].id))
                for slug in ladder
            ]
        finally:
            await session.rollback()
            await session.close()

        for (lower_slug, lower), (upper_slug, upper) in itertools.pairwise(
            zip(ladder, sets, strict=True)
        ):
            assert lower < upper, f"{lower_slug.value} is not a strict subset of {upper_slug.value}"

    async def test_a_specialist_cannot_approve_or_touch_credentials(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """The human-in-the-loop gate is a separate permission for this reason."""
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = {role.slug: role for role in await RoleRepository(session).list_all()}
            codes = set(
                await RolePermissionRepository(session).list_permission_codes_for_role(
                    roles[SystemRoleSlug.SEO_SPECIALIST.value].id
                )
            )
        finally:
            await session.rollback()
            await session.close()

        assert Perm.SUBMISSION_APPROVE.value not in codes
        assert not any(code.startswith("credential.") for code in codes)

    async def test_a_viewer_cannot_read_credentials_or_the_audit_trail(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            roles = {role.slug: role for role in await RoleRepository(session).list_all()}
            codes = set(
                await RolePermissionRepository(session).list_permission_codes_for_role(
                    roles[SystemRoleSlug.VIEWER.value].id
                )
            )
        finally:
            await session.rollback()
            await session.close()

        assert Perm.CREDENTIAL_READ.value not in codes
        assert Perm.AUDIT_READ.value not in codes


class TestSeedIsIdempotent:
    async def test_re_running_the_seed_changes_nothing(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        resources: AppResources,
        tenant_a: TenantFixture,
    ) -> None:
        """A deploy that runs the seed twice must not duplicate or drop grants."""
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id)
        try:
            roles = RoleRepository(session)
            grants = RolePermissionRepository(session)
            before_ids = {role.slug: role.id for role in await roles.list_all()}
            before_grants = {
                slug: set(await grants.list_permission_codes_for_role(role_id))
                for slug, role_id in before_ids.items()
            }

            services = ServiceFactory(session=session, resources=resources)
            await services.tenant_service.seed_system_roles(tenant_a.tenant_id)
            await session.flush()

            after_ids = {role.slug: role.id for role in await roles.list_all()}
            after_grants = {
                slug: set(await grants.list_permission_codes_for_role(role_id))
                for slug, role_id in after_ids.items()
            }

            assert after_ids == before_ids
            assert after_grants == before_grants
        finally:
            await session.rollback()
            await session.close()


class TestEffectivePermissions:
    async def test_the_owner_resolves_to_the_full_permission_set(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Resolved per request, so a revoked role takes effect immediately."""
        async with session_factory() as session:
            codes = await EffectivePermissionRepository(session).codes_for_user_in_tenant(
                user_id=tenant_a.owner.id, tenant_id=tenant_a.tenant_id
            )
        assert codes == frozenset(perm.value for perm in ALL_PERMISSIONS)

    async def test_permissions_do_not_cross_workspaces(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """Owning workspace A grants nothing at all in workspace B."""
        async with session_factory() as session:
            codes = await EffectivePermissionRepository(session).codes_for_user_in_tenant(
                user_id=tenant_a.owner.id, tenant_id=tenant_b.tenant_id
            )
        assert codes == frozenset()

    async def test_a_suspended_member_keeps_their_roles_but_gains_nothing(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Suspension is reversible: the assignment rows survive it."""
        session = session_factory()
        await session.set_tenant_context(tenant_id=tenant_a.tenant_id)
        try:
            membership = await session.get(TenantMembership, tenant_a.owner_membership.id)
            assert membership is not None
            membership.status = MembershipStatus.SUSPENDED.value
            await session.flush()

            codes = await EffectivePermissionRepository(session).codes_for_user_in_tenant(
                user_id=tenant_a.owner.id, tenant_id=tenant_a.tenant_id
            )
            assert codes == frozenset()

            assigned = await MembershipRoleRepository(session).list_roles_for_membership(
                membership.id
            )
            assert [role.slug for role in assigned] == [SystemRoleSlug.OWNER.value]
        finally:
            await session.rollback()
            await session.close()

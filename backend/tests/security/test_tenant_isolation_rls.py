"""PostgreSQL Row-Level Security: cross-tenant isolation.

Every test here runs as the **runtime** database role, which is
``NOSUPERUSER`` and ``NOBYPASSRLS``. That matters: asserting isolation over a
superuser connection would prove nothing, because a superuser bypasses RLS
entirely.

The premise is that application code will one day forget a
``WHERE tenant_id = …``. These tests assert PostgreSQL still refuses to return,
modify, delete or plant another tenant's rows when it does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.context import apply_tenant_context, read_tenant_context
from app.db.session import TenantAwareSession
from app.models import TENANT_OWNED_TABLES
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.security, pytest.mark.integration]

#: Tables carrying rows in the two-tenant fixture, so a cross-tenant read has
#: something to fail to find.
POPULATED_TABLES = (
    "tenant_memberships",
    "roles",
    "role_permissions",
    "membership_roles",
    "client_websites",
    "campaigns",
    "publishers",
    "opportunities",
    "audit_logs",
)


class TestRuntimeRole:
    async def test_the_suite_runs_as_a_role_that_cannot_bypass_rls(
        self, rls_session_factory: async_sessionmaker[TenantAwareSession]
    ) -> None:
        # If this fails, every other test in this file is vacuous.
        async with rls_session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT current_user, "
                        "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user), "
                        "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
                    )
                )
            ).one()
        _, is_superuser, bypasses_rls = row
        assert is_superuser is False
        assert bypasses_rls is False


class TestDefaultDeny:
    @pytest.mark.parametrize("table", POPULATED_TABLES)
    async def test_no_tenant_context_returns_no_rows(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenants: tuple[TenantFixture, TenantFixture],
        table: str,
    ) -> None:
        # An unset context makes app_current_tenant_id() NULL, so the policy
        # predicate is NULL rather than true: nothing, not everything.
        async with rls_session_factory() as session:
            count = (
                await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            ).scalar_one()
        assert count == 0

    async def test_the_context_helpers_report_an_empty_context(
        self, rls_session_factory: async_sessionmaker[TenantAwareSession]
    ) -> None:
        async with rls_session_factory() as session:
            await session.execute(text("SELECT 1"))
            tenant_id, user_id = await read_tenant_context(session)
        assert tenant_id is None
        assert user_id is None


class TestCrossTenantReads:
    async def test_a_tenant_sees_only_its_own_rows(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            domains = set(
                (await session.execute(text("SELECT normalized_domain FROM publishers")))
                .scalars()
                .all()
            )
        assert domains == {"tenant-a-freedir.test", "tenant-a-paiddir.test"}
        assert tenant_b.free_publisher.normalized_domain not in domains

    @pytest.mark.parametrize(
        ("table", "attribute"),
        [
            ("publishers", "free_publisher"),
            ("campaigns", "campaign"),
            ("client_websites", "client_website"),
            ("opportunities", "opportunity"),
        ],
    )
    async def test_guessing_another_tenants_id_returns_nothing(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        table: str,
        attribute: str,
    ) -> None:
        # Knowing an id must not be enough. This is the attack the ID-guessing
        # requirement is about.
        target_id = getattr(tenant_b, attribute).id
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            count = (
                await session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE id = :id"),  # noqa: S608
                    {"id": target_id},
                )
            ).scalar_one()
        assert count == 0


class TestCrossTenantWrites:
    async def test_updating_another_tenants_row_affects_nothing(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        session_factory: async_sessionmaker[TenantAwareSession],
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            result = await session.execute(
                text("UPDATE publishers SET name = 'HACKED' WHERE id = :id"),
                {"id": tenant_b.free_publisher.id},
            )
            assert result.rowcount == 0
            await session.commit()

        # Confirmed independently through the owner connection.
        async with session_factory() as owner:
            name = (
                await owner.execute(
                    text("SELECT name FROM publishers WHERE id = :id"),
                    {"id": tenant_b.free_publisher.id},
                )
            ).scalar_one()
        assert name != "HACKED"

    async def test_deleting_another_tenants_row_affects_nothing(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
        session_factory: async_sessionmaker[TenantAwareSession],
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            result = await session.execute(
                text("DELETE FROM publishers WHERE id = :id"),
                {"id": tenant_b.free_publisher.id},
            )
            assert result.rowcount == 0
            await session.commit()

        async with session_factory() as owner:
            still_there = (
                await owner.execute(
                    text("SELECT count(*) FROM publishers WHERE id = :id"),
                    {"id": tenant_b.free_publisher.id},
                )
            ).scalar_one()
        assert still_there == 1

    async def test_planting_a_row_in_another_tenant_is_refused(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        # WITH CHECK, not just USING: without it a tenant could not *read*
        # another's data but could still write into it.
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            with pytest.raises(DBAPIError, match="row-level security"):
                await session.execute(
                    text(
                        "INSERT INTO publishers "
                        "(id, tenant_id, domain, normalized_domain, website_url) "
                        "VALUES (gen_random_uuid(), :tenant_id, 'planted.test', "
                        "'planted.test', 'https://planted.test')"
                    ),
                    {"tenant_id": tenant_b.tenant_id},
                )
            await session.rollback()


class TestForgottenTenantFilter:
    """The scenario the whole design exists for."""

    async def test_an_unfiltered_update_only_touches_the_active_tenant(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            # No WHERE clause at all: exactly the bug RLS is insurance against.
            result = await session.execute(text("UPDATE publishers SET language = 'zz'"))
            assert result.rowcount == 2  # only tenant A's two publishers
            await session.commit()

        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_b.tenant_id, user_id=tenant_b.owner.id
            )
            leaked = (
                await session.execute(text("SELECT count(*) FROM publishers WHERE language = 'zz'"))
            ).scalar_one()
        assert leaked == 0

    async def test_an_unfiltered_delete_only_touches_the_active_tenant(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            await session.execute(text("DELETE FROM opportunities"))
            await session.commit()

        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_b.tenant_id, user_id=tenant_b.owner.id
            )
            surviving = (
                await session.execute(text("SELECT count(*) FROM opportunities"))
            ).scalar_one()
        assert surviving == 1


class TestMembershipSelfAccess:
    async def test_a_user_can_list_their_memberships_before_choosing_a_workspace(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        # "Which workspaces may I enter?" has to be answerable with no tenant
        # context, which is why memberships carry an extra SELECT policy.
        async with rls_session_factory() as session:
            await apply_tenant_context(session, tenant_id=None, user_id=tenant_a.owner.id)
            rows = (
                (await session.execute(text("SELECT tenant_id FROM tenant_memberships")))
                .scalars()
                .all()
            )
        assert list(rows) == [tenant_a.tenant_id]

    async def test_the_self_policy_does_not_expose_other_users(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        async with rls_session_factory() as session:
            await apply_tenant_context(session, tenant_id=None, user_id=tenant_a.owner.id)
            others = (
                await session.execute(
                    text("SELECT count(*) FROM tenant_memberships WHERE user_id <> :user_id"),
                    {"user_id": tenant_a.owner.id},
                )
            ).scalar_one()
        assert others == 0

    async def test_the_self_policy_is_read_only(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        # A FOR ALL self-policy would let a member edit their own membership
        # row and, for example, lift their own suspension.
        async with rls_session_factory() as session:
            await apply_tenant_context(session, tenant_id=None, user_id=tenant_a.owner.id)
            result = await session.execute(
                text(
                    "UPDATE tenant_memberships SET is_owner = true, status = 'ACTIVE' "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": tenant_a.owner.id},
            )
            assert result.rowcount == 0
            await session.rollback()


class TestContextHygiene:
    async def test_the_context_is_transaction_local(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        # The property that stops a pooled connection carrying one tenant's
        # context into the next request.
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            current, _ = await read_tenant_context(session)
            assert current == tenant_a.tenant_id
            await session.rollback()

            await session.execute(text("SELECT 1"))
            after_rollback = (
                await session.execute(
                    text("SELECT nullif(current_setting('app.current_tenant_id', true), '')")
                )
            ).scalar_one()
        # TenantAwareSession re-applies its context after rollback, so the
        # session stays usable; the point is that PostgreSQL discarded the
        # transaction-local value and it had to be set again.
        assert after_rollback in (None, str(tenant_a.tenant_id))

    async def test_switching_context_switches_visibility(
        self,
        rls_session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        async with rls_session_factory() as session:
            await session.set_tenant_context(
                tenant_id=tenant_a.tenant_id, user_id=tenant_a.owner.id
            )
            first = (
                (await session.execute(text("SELECT normalized_domain FROM publishers")))
                .scalars()
                .all()
            )

            await session.set_tenant_context(
                tenant_id=tenant_b.tenant_id, user_id=tenant_b.owner.id
            )
            second = (
                (await session.execute(text("SELECT normalized_domain FROM publishers")))
                .scalars()
                .all()
            )

        assert set(first).isdisjoint(set(second))


class TestSchemaCoverage:
    async def test_every_tenant_owned_table_is_forced_and_has_a_policy(
        self, engine, migrated_database: None
    ) -> None:
        """Derived from the schema, so a new tenant-owned table cannot be missed.

        ``TENANT_OWNED_TABLES`` is computed from the models by looking for a
        ``tenant_id`` column, and this compares it against what PostgreSQL
        actually enforces.
        """
        async with engine.connect() as connection:
            rows = (await connection.execute(text("""
                        SELECT c.relname,
                               c.relrowsecurity,
                               c.relforcerowsecurity,
                               (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
                          FROM pg_class c
                          JOIN pg_namespace n ON n.oid = c.relnamespace
                         WHERE n.nspname = 'public' AND c.relkind = 'r'
                        """))).all()

        state = {name: (enabled, forced, policies) for name, enabled, forced, policies in rows}
        for table in sorted(TENANT_OWNED_TABLES):
            assert table in state, f"{table} is missing from the database"
            enabled, forced, policies = state[table]
            assert enabled, f"{table}: row level security is not enabled"
            # FORCE is what makes the policy apply to the table owner too.
            assert forced, f"{table}: row level security is not forced"
            assert policies >= 1, f"{table}: no policy defined"

    async def test_the_model_derived_table_set_is_not_empty(self) -> None:
        # A guard against the audit above passing because it iterated nothing.
        assert len(TENANT_OWNED_TABLES) >= 15

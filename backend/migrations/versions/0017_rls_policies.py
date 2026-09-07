"""Row-Level Security policies for every tenant-owned table.

This is the last line of tenant isolation. The application already filters by
``tenant_id`` in every repository, but that is code, and code has bugs. These
policies make PostgreSQL itself refuse to return, modify, delete or plant
another tenant's rows even if an application query forgets its ``WHERE``.

Three details carry the guarantee:

* ``ENABLE`` *and* ``FORCE`` — ``ENABLE`` alone exempts the table owner, which
  in development is usually the same role that runs the app. ``FORCE`` closes
  that. The only remaining bypass is a cluster superuser, which the runtime
  role deliberately is not (see 0018 and docker/postgres/init).
* ``USING`` *and* ``WITH CHECK`` — ``USING`` filters reads, updates and
  deletes; ``WITH CHECK`` rejects an INSERT or UPDATE that would write a
  foreign ``tenant_id``. Without the second half a tenant could not read
  another's data but could still plant rows in it.
* Default deny — with no context, ``app_current_tenant_id()`` is NULL, so
  ``tenant_id = NULL`` is NULL rather than true and the row is invisible. An
  unscoped session sees nothing instead of everything.

``tenant_memberships`` additionally gets a **SELECT-only** self-access policy,
because "which tenants may I enter?" must be answerable before any tenant is
chosen. It is restricted to SELECT on purpose: a FOR ALL self-policy would let
a user UPDATE their own membership row and, for example, lift their own
suspension.

The revision ends with an assertion block that fails the migration if any table
carrying a ``tenant_id`` column was left unprotected, so adding a tenant-owned
table without a policy cannot ship silently.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every tenant-owned table, in creation order. Kept explicit so the protected
#: set is reviewable in one place; completeness is asserted below.
TENANT_OWNED_TABLES: tuple[str, ...] = (
    "tenant_memberships",
    "roles",
    "role_permissions",
    "membership_roles",
    "client_websites",
    "campaigns",
    "discovery_runs",
    "publishers",
    "opportunities",
    "submissions",
    "generated_contents",
    "credentials",
    "tenant_ai_configs",
    "ai_usage_records",
    "audit_logs",
    "jobs",
    "idempotency_keys",
)

#: Intentionally excluded: global identity tables with no ``tenant_id``. They
#: must be reachable before a tenant is selected (login, refresh, tenant list,
#: workspace creation), so a tenant predicate would break authentication rather
#: than protect it. See docs/ARCHITECTURE.md §5.5.
GLOBAL_TABLES: tuple[str, ...] = ("users", "tenants", "permissions", "refresh_sessions")


def upgrade() -> None:
    for table in TENANT_OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (tenant_id = app_current_tenant_id())
                WITH CHECK (tenant_id = app_current_tenant_id())
            """)

    # Pre-tenant read access to one's own memberships. SELECT only.
    op.execute("""
        CREATE POLICY tenant_memberships_self_read ON tenant_memberships
            FOR SELECT
            USING (user_id = app_current_user_id())
        """)

    op.execute("""
        COMMENT ON POLICY tenant_memberships_self_read ON tenant_memberships IS
            'Lets a user enumerate the tenants they may enter before a tenant '
            'context exists. SELECT only: writes still require tenant context, '
            'so a member cannot edit their own membership (e.g. lift a '
            'suspension) without it.'
        """)

    # Completeness assertion: any table with a tenant_id column must be both
    # FORCEd and covered by at least one policy. Runs inside the migration's
    # transaction, so a violation aborts the upgrade.
    op.execute("""
        DO $$
        DECLARE
            offending text;
        BEGIN
            SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
              INTO offending
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
               AND c.relkind = 'r'
               AND EXISTS (
                     SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = c.oid
                        AND a.attname = 'tenant_id'
                        AND a.attnum > 0
                        AND NOT a.attisdropped
                   )
               AND (
                     NOT c.relrowsecurity
                     OR NOT c.relforcerowsecurity
                     OR NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)
                   );

            IF offending IS NOT NULL THEN
                RAISE EXCEPTION
                    'tenant-owned tables without forced RLS and a policy: %', offending;
            END IF;
        END
        $$
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_memberships_self_read ON tenant_memberships")
    for table in reversed(TENANT_OWNED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

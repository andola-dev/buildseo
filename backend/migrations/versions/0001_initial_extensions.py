"""Initial database: extensions and shared SQL helpers.

Creates the pieces every later revision depends on:

* ``citext`` for case-insensitive email uniqueness enforced by the database.
* ``pgcrypto`` for ``gen_random_uuid()``, available as a server-side fallback
  even though the application generates UUIDv7 ids itself.
* ``app_current_tenant_id()`` / ``app_current_user_id()`` — the accessors every
  RLS policy is written against. Defining them once means a policy is a single
  readable comparison, and the ``nullif`` makes an unset context NULL so the
  predicate is false: default deny.
* ``set_updated_at()`` — keeps ``updated_at`` honest even for raw SQL updates
  that bypass the ORM.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # STABLE (not IMMUTABLE): the value can differ between statements in a
    # transaction, but not within one, which is what the planner needs to use
    # these inside a policy without re-evaluating per row.
    op.execute("""
        CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
            SELECT nullif(current_setting('app.current_tenant_id', true), '')::uuid
        $$
        """)
    op.execute("""
        CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
            SELECT nullif(current_setting('app.current_user_id', true), '')::uuid
        $$
        """)
    op.execute("""
        COMMENT ON FUNCTION app_current_tenant_id() IS
            'Active tenant for the current transaction, set server-side by the '
            'application from a validated membership. NULL when unset, which '
            'makes every RLS policy predicate false (default deny).'
        """)

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
        """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")
    # Extensions are intentionally left in place: they may be shared with
    # other schemas in the same database, and dropping citext would cascade
    # to any remaining column that uses it.

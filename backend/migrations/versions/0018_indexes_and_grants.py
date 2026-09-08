"""Runtime-role privileges and remaining performance indexes.

Privileges are granted to the role named by ``DB_APP_ROLE`` (default
``buildseo_app``), which is the NOSUPERUSER/NOBYPASSRLS role the API and worker
connect as. If that role does not exist — a bare CI database, a developer who
runs everything as the owner — the grants are skipped with a notice rather than
failing, so one revision set works in every environment.

The runtime role deliberately gets DML only: no CREATE, no DDL, no ownership.
It cannot drop a policy, disable RLS, or reshape a table, which means an
application-level SQL injection cannot escalate into removing its own
isolation.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID_ROLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _app_role() -> str:
    """Resolve the runtime role from Alembic attributes, then the environment.

    ``DO`` blocks cannot take bound query parameters, so the role name is
    interpolated directly into the block below. It is validated as a plain
    SQL identifier here to keep that interpolation safe.
    """
    configured = context.config.attributes.get("db_app_role")
    role = str(configured or os.environ.get("DB_APP_ROLE") or "buildseo_app")
    if not _VALID_ROLE_NAME.fullmatch(role):
        raise ValueError(f"invalid DB_APP_ROLE {role!r}: must be a plain SQL identifier")
    return role


def upgrade() -> None:
    # ------------------------------------------------------- search indexes --
    # Case-insensitive prefix/substring search over names and domains. The
    # trigram indexes make ILIKE '%term%' usable, which a plain B-tree cannot
    # serve, and are the difference between a fast and a sequential-scan search
    # once a tenant holds tens of thousands of publishers.
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute(
        "CREATE INDEX ix_publishers_name_trgm ON publishers "
        "USING gin (name gin_trgm_ops) WHERE name IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_publishers_normalized_domain_trgm ON publishers "
        "USING gin (normalized_domain gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_client_websites_name_trgm ON client_websites "
        "USING gin (name gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_campaigns_name_trgm ON campaigns USING gin (name gin_trgm_ops)")

    # Cross-tenant operational sweeps (expired-key retention, session reaper)
    # are keyed on time alone, so they need indexes without a tenant prefix.
    op.create_index(
        "ix_opportunities_status_updated_at",
        "opportunities",
        ["status", "updated_at"],
        postgresql_where=sa.text("status IN ('SUBMITTED', 'PUBLISHED')"),
    )

    # ---------------------------------------------------------------- grants --
    role = _app_role()
    op.execute(f"""
            DO $do$
            DECLARE
                app_role text := '{role}';
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
                    RAISE NOTICE
                        'runtime role % not present; skipping grants. Create it before '
                        'pointing the application at this database.', app_role;
                    RETURN;
                END IF;

                EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_role);
                EXECUTE format(
                    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I',
                    app_role
                );
                EXECUTE format(
                    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', app_role
                );
                -- Future tables created by later migrations inherit these.
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
                    app_role
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
                    app_role
                );

                -- The audit trail is append-only for the application: it may
                -- write and read, never rewrite or erase its own history.
                EXECUTE format('REVOKE UPDATE, DELETE ON audit_logs FROM %I', app_role);
                EXECUTE format('REVOKE UPDATE, DELETE ON ai_usage_records FROM %I', app_role);

                -- The runtime role must not be able to reshape the schema or
                -- remove the policies that constrain it.
                EXECUTE format('REVOKE CREATE ON SCHEMA public FROM %I', app_role);

                RAISE NOTICE 'granted runtime DML privileges to %', app_role;
            END
            $do$
            """)


def downgrade() -> None:
    role = _app_role()
    op.execute(f"""
            DO $do$
            DECLARE
                app_role text := '{role}';
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
                    RETURN;
                END IF;
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                    'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM %I',
                    app_role
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                    'REVOKE USAGE, SELECT ON SEQUENCES FROM %I',
                    app_role
                );
                EXECUTE format(
                    'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', app_role
                );
                EXECUTE format(
                    'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', app_role
                );
                EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', app_role);
            END
            $do$
            """)

    op.drop_index("ix_opportunities_status_updated_at", table_name="opportunities")
    op.execute("DROP INDEX IF EXISTS ix_campaigns_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_client_websites_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_publishers_normalized_domain_trgm")
    op.execute("DROP INDEX IF EXISTS ix_publishers_name_trgm")

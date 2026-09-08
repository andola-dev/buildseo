"""Alembic environment.

Runs migrations over an **async** engine (asyncpg) via ``run_sync``, so the
project has exactly one database driver and no synchronous SQLAlchemy anywhere.

The connection URL and the runtime role name come from application settings,
never from ``alembic.ini``, so credentials stay out of version control and the
same migrations run unchanged in CI, development and production.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.config.settings import get_settings
from app.db.base import Base
from app.models import ALL_MODELS  # noqa: F401 - registers every table on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# A caller (the test suite's migrated_database fixture) may have already
# pointed this Config at a different database, e.g. to keep migrations run
# by tests off the development database. Only fall back to the process's
# own settings when nothing more specific was configured.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.alembic_url)
#: Consumed by the grants revision so it can target the runtime role.
config.attributes.setdefault("db_app_role", settings.db_app_role)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate focused on this application's own tables."""
    if type_ == "table" and name in {"alembic_version"}:
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (``alembic upgrade --sql``)."""
    context.configure(
        url=settings.alembic_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        # One transaction per migration run: a failure leaves no half-applied
        # schema, which matters because the RLS revision must be all-or-nothing.
        transaction_per_migration=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

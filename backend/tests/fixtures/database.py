"""Database fixtures.

The test database is built by running **Alembic from empty**, which makes
"migrations apply cleanly from scratch" an assertion of every DB test run
rather than a separate thing to remember.

Two engines are provided, and the distinction is the point:

``engine``
    Connects as the migration/owner role. Used to seed fixtures and to assert
    what is really in the database, independent of any policy.

``rls_engine``
    Connects as the runtime role, which is ``NOSUPERUSER`` and ``NOBYPASSRLS``.
    Every isolation test uses this one — asserting isolation through a
    superuser connection would prove nothing, because a superuser bypasses RLS
    entirely.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.bootstrap import AppResources, build_resources
from app.config.settings import Settings
from app.db.session import TenantAwareSession, create_engine, create_session_factory

#: Override with TEST_DATABASE_URL / TEST_APP_DATABASE_URL in CI.
DEFAULT_OWNER_URL = "postgresql+asyncpg://buildseo:buildseo@localhost:5432/buildseo_test"
DEFAULT_APP_URL = "postgresql+asyncpg://buildseo_app:buildseo_app@localhost:5432/buildseo_test"

TEST_JWT_SECRET = "test-secret-not-used-outside-the-suite-0123456789"
TEST_ENCRYPTION_KEY = "dGVzdC1vbmx5LWtleS0zMi1ieXRlcy1sb25nLXh4eHg="


def _owner_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_OWNER_URL)


def _app_url() -> str:
    return os.environ.get("TEST_APP_DATABASE_URL", DEFAULT_APP_URL)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings for the suite, pinned to the test database."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_url=_app_url(),
        database_migration_url=_owner_url(),
        jwt_secret=TEST_JWT_SECRET,
        encryption_key=TEST_ENCRYPTION_KEY,
        # Deterministic tests: no throttling, and the cheapest Argon2 settings
        # that still exercise the real KDF.
        rate_limit_enabled=False,
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        log_json=False,
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
def migrated_database(settings: Settings) -> Iterator[None]:
    """Build the schema by running every migration against an empty database.

    Downgrading to base first means a re-run starts genuinely clean, so a
    migration that only works on top of an existing schema fails here.
    """
    config = Config(str(os.path.dirname(__file__) + "/../../alembic.ini"))
    config.set_main_option("script_location", "migrations")
    config.set_main_option("sqlalchemy.url", settings.alembic_url)
    config.attributes["db_app_role"] = settings.db_app_role

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield
    # Left in place after the run so a failure can be inspected.


@pytest_asyncio.fixture(scope="session")
async def engine(settings: Settings, migrated_database: None) -> AsyncIterator[AsyncEngine]:
    """Owner-role engine, for seeding and for policy-independent assertions."""
    owner = create_engine(settings, url=settings.alembic_url)
    yield owner
    await owner.dispose()


@pytest_asyncio.fixture(scope="session")
async def rls_engine(settings: Settings, migrated_database: None) -> AsyncIterator[AsyncEngine]:
    """Runtime-role engine. NOBYPASSRLS, so policies actually apply."""
    app_engine = create_engine(settings)
    yield app_engine
    await app_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[TenantAwareSession]:
    return create_session_factory(engine)


@pytest_asyncio.fixture
async def rls_session_factory(
    rls_engine: AsyncEngine,
) -> async_sessionmaker[TenantAwareSession]:
    return create_session_factory(rls_engine)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[TenantAwareSession],
) -> AsyncIterator[TenantAwareSession]:
    """A session whose work is rolled back, so tests do not affect each other."""
    session = session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def resources(settings: Settings, rls_engine: AsyncEngine) -> AsyncIterator[AppResources]:
    """The container the application runs on, bound to the **runtime** role.

    This is deliberately ``rls_engine``, not ``engine``. The API suite drives
    the real app through this container, so whichever engine it holds is the
    one every endpoint queries with. Bound to the owner role — a SUPERUSER,
    which bypasses Row-Level Security entirely — the whole API suite would
    pass with RLS effectively switched off, and could not observe a bug in the
    tenant-context handshake at all. That is exactly what happened: 112 green
    API tests alongside an app in which every tenant-scoped endpoint returned
    403 for a legitimate member.

    Fixtures still *seed* through the owner engine (``session_factory``),
    because setting up two tenants' data is not what is under test. Only the
    application's own queries go through the confined role.
    """
    container = build_resources(settings, engine=rls_engine)
    yield container
    # The engine belongs to the session-scoped fixture, so only the HTTP client
    # is closed here.
    await container.http_client.aclose()


@pytest.fixture(scope="session")
def sync_dsn(settings: Settings) -> str:
    """A psycopg-style DSN, for the few checks that read catalog tables."""
    parts = urlsplit(settings.sync_database_url(settings.alembic_url))
    return urlunsplit(parts)

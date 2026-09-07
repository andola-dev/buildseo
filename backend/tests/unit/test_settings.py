"""Configuration validation.

Requires pydantic-settings, so this module needs the full dependency set.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator

import pytest

from app.config.settings import Settings

pytestmark = pytest.mark.unit

STRONG_SECRET = "x" * 48
STRONG_KEY = base64.b64encode(b"k" * 32).decode()


@pytest.fixture(autouse=True)
def isolated_env() -> Iterator[None]:
    """Run each test against a clean environment.

    Settings read the process environment and a .env file, so a developer's
    local values must not influence the result.
    """
    saved = dict(os.environ)
    for key in list(os.environ):
        if key.split("_")[0] in {
            "APP",
            "DATABASE",
            "DB",
            "JWT",
            "ENCRYPTION",
            "CORS",
            "LOG",
            "RATE",
            "HTTP",
            "WORKER",
            "PASSWORD",
            "ARGON2",
            "DEFAULT",
            "MAX",
            "FREE",
            "DOCS",
            "SECURE",
            "TRUSTED",
            "API",
        }:
            del os.environ[key]
    yield
    os.environ.clear()
    os.environ.update(saved)


def build(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


class TestDefaults:
    def test_local_defaults_are_usable(self) -> None:
        settings = build()
        assert settings.app_env == "local"
        assert settings.jwt_access_token_expire_minutes == 15
        assert settings.free_only_enforced is True


class TestEncryptionKey:
    def test_accepts_a_32_byte_base64_key(self) -> None:
        assert len(build(encryption_key=STRONG_KEY).master_key) == 32

    @pytest.mark.parametrize(
        "value",
        [
            "not-base64!!",
            base64.b64encode(b"short").decode(),
            base64.b64encode(b"x" * 64).decode(),
        ],
    )
    def test_rejects_a_key_of_the_wrong_shape(self, value: str) -> None:
        with pytest.raises(ValueError):
            build(encryption_key=value)


class TestCorsParsing:
    def test_accepts_a_comma_separated_list(self) -> None:
        settings = build(cors_origins="http://a.test, http://b.test")
        assert settings.cors_origins == ["http://a.test", "http://b.test"]

    def test_an_empty_value_is_no_origins(self) -> None:
        assert build(cors_origins="") == build(cors_origins="")


class TestProductionHardening:
    """A misconfigured production deployment must fail to start, not run."""

    def test_refuses_the_placeholder_jwt_secret(self) -> None:
        with pytest.raises(ValueError, match="JWT_SECRET"):
            build(app_env="production", encryption_key=STRONG_KEY)

    def test_refuses_the_placeholder_encryption_key(self) -> None:
        with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
            build(app_env="production", jwt_secret=STRONG_SECRET)

    def test_refuses_a_short_jwt_secret(self) -> None:
        with pytest.raises(ValueError, match="at least 32"):
            build(app_env="production", jwt_secret="short", encryption_key=STRONG_KEY)

    def test_refuses_debug_mode(self) -> None:
        with pytest.raises(ValueError, match="DEBUG"):
            build(
                app_env="production",
                jwt_secret=STRONG_SECRET,
                encryption_key=STRONG_KEY,
                debug=True,
            )

    def test_refuses_request_body_logging(self) -> None:
        with pytest.raises(ValueError, match="LOG_REQUEST_BODY"):
            build(
                app_env="production",
                jwt_secret=STRONG_SECRET,
                encryption_key=STRONG_KEY,
                log_request_body=True,
            )

    def test_refuses_a_wildcard_cors_origin(self) -> None:
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            build(
                app_env="production",
                jwt_secret=STRONG_SECRET,
                encryption_key=STRONG_KEY,
                cors_origins="*",
            )

    def test_accepts_a_properly_configured_production_environment(self) -> None:
        settings = build(
            app_env="production",
            jwt_secret=STRONG_SECRET,
            encryption_key=STRONG_KEY,
            cors_origins="https://app.example.com",
        )
        assert settings.is_production

    def test_local_and_test_environments_skip_the_guard(self) -> None:
        # Otherwise every developer would need real secrets to run the suite.
        for env in ("local", "test"):
            assert build(app_env=env, debug=True).app_env == env


class TestDatabaseUrls:
    def test_rejects_a_non_postgres_url(self) -> None:
        with pytest.raises(ValueError, match="PostgreSQL"):
            build(database_url="mysql://localhost/x")

    def test_alembic_prefers_the_migration_url(self) -> None:
        settings = build(
            database_url="postgresql+asyncpg://app@localhost/db",
            database_migration_url="postgresql+asyncpg://owner@localhost/db",
        )
        assert settings.alembic_url == "postgresql+asyncpg://owner@localhost/db"

    def test_alembic_falls_back_to_the_runtime_url(self) -> None:
        settings = build(database_url="postgresql+asyncpg://app@localhost/db")
        assert settings.alembic_url == settings.database_url

    def test_sync_url_strips_the_async_driver(self) -> None:
        settings = build(database_url="postgresql+asyncpg://app@localhost/db")
        assert settings.sync_database_url() == "postgresql://app@localhost/db"


class TestPageSizes:
    def test_the_default_page_size_cannot_exceed_the_maximum(self) -> None:
        with pytest.raises(ValueError, match="page_size"):
            build(default_page_size=200, max_page_size=100)

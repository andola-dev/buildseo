"""Application settings.

All configuration is read from the environment (optionally seeded from a local
``.env`` file for development). No secret ever has a usable default: the
production guard in :meth:`Settings.validate_production_hardening` refuses to
start an app that is still carrying development placeholders.
"""

from __future__ import annotations

import base64
import binascii
import json
from functools import lru_cache
from typing import Annotated, Any, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.crypto.keys import MASTER_KEY_BYTES

AppEnv = Literal["local", "test", "development", "staging", "production"]

# Placeholder secrets shipped in ``.env.example``. Refused outside local/test.
_DEV_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "secret",
        "dev-secret-not-for-production-use-only-0123456789",
        "dGhpcy1pcy1hLWRldi1vbmx5LWtleS0zMi1ieXRlcyE=",
    }
)


class Settings(BaseSettings):
    """Typed, validated application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=None,
    )

    # ----------------------------------------------------------------- app --
    app_env: AppEnv = "local"
    app_name: str = "BuildSEO API"
    app_description: str = (
        "Multi-tenant SaaS backend for discovering, qualifying, managing and "
        "submitting links to free online listing and directory sites."
    )
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True

    # ------------------------------------------------------------ database --
    database_url: str = "postgresql+asyncpg://buildseo_app:buildseo_app@localhost:5432/buildseo"
    #: Optional privileged URL used only by Alembic. Falls back to ``database_url``.
    database_migration_url: str | None = None
    #: Runtime database role that must be ``NOBYPASSRLS``; grants target this role.
    db_app_role: str = "buildseo_app"
    db_pool_size: Annotated[int, Field(ge=1, le=200)] = 10
    db_max_overflow: Annotated[int, Field(ge=0, le=200)] = 10
    db_pool_timeout: Annotated[float, Field(gt=0)] = 30.0
    db_pool_recycle_seconds: Annotated[int, Field(ge=-1)] = 1800
    db_pool_pre_ping: bool = True
    db_statement_timeout_ms: Annotated[int, Field(ge=0)] = 30_000
    db_echo: bool = False

    # ------------------------------------------------------------------ jwt --
    jwt_secret: SecretStr = SecretStr("dev-secret-not-for-production-use-only-0123456789")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "buildseo"
    jwt_audience: str = "buildseo-api"
    jwt_access_token_expire_minutes: Annotated[int, Field(ge=1, le=1440)] = 15
    jwt_refresh_token_expire_days: Annotated[int, Field(ge=1, le=365)] = 14
    #: Clock skew tolerance when validating ``exp``/``nbf``.
    jwt_leeway_seconds: Annotated[int, Field(ge=0, le=300)] = 10

    # ----------------------------------------------------------- passwords --
    password_min_length: Annotated[int, Field(ge=8, le=256)] = 12
    password_max_length: Annotated[int, Field(ge=64, le=1024)] = 128
    argon2_time_cost: Annotated[int, Field(ge=1, le=32)] = 3
    argon2_memory_cost_kib: Annotated[int, Field(ge=8192, le=1_048_576)] = 65_536
    argon2_parallelism: Annotated[int, Field(ge=1, le=32)] = 4
    argon2_hash_length: Annotated[int, Field(ge=16, le=128)] = 32

    # ---------------------------------------------------------- encryption --
    #: base64-encoded 32-byte master key (KEK) for envelope encryption.
    encryption_key: SecretStr = SecretStr("dGhpcy1pcy1hLWRldi1vbmx5LWtleS0zMi1ieXRlcyE=")
    encryption_key_version: Annotated[int, Field(ge=1)] = 1

    # --------------------------------------------------------------- http ---
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    cors_allow_credentials: bool = True
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    secure_headers_enabled: bool = True

    # ------------------------------------------------------------ logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True
    log_request_body: bool = False  # never enable in production

    # ------------------------------------------------------- rate limiting --
    rate_limit_enabled: bool = True
    rate_limit_requests: Annotated[int, Field(ge=1)] = 300
    rate_limit_window_seconds: Annotated[int, Field(ge=1)] = 60
    rate_limit_auth_requests: Annotated[int, Field(ge=1)] = 10
    rate_limit_auth_window_seconds: Annotated[int, Field(ge=1)] = 60

    # -------------------------------------------------- outbound http client --
    http_timeout_seconds: Annotated[float, Field(gt=0)] = 15.0
    http_connect_timeout_seconds: Annotated[float, Field(gt=0)] = 5.0
    http_max_connections: Annotated[int, Field(ge=1)] = 100
    http_max_keepalive_connections: Annotated[int, Field(ge=1)] = 20
    http_max_retries: Annotated[int, Field(ge=0, le=10)] = 2
    http_max_response_bytes: Annotated[int, Field(ge=1024)] = 5 * 1024 * 1024
    http_follow_redirects: bool = True
    http_max_redirects: Annotated[int, Field(ge=0, le=20)] = 5
    http_user_agent: str = "BuildSEO/0.1 (+https://buildseo.example/bot)"

    # ------------------------------------------------------------ workers ---
    worker_poll_interval_seconds: Annotated[float, Field(gt=0)] = 2.0
    worker_batch_size: Annotated[int, Field(ge=1, le=100)] = 5
    worker_max_attempts: Annotated[int, Field(ge=1, le=20)] = 3
    worker_retry_backoff_seconds: Annotated[int, Field(ge=1)] = 30
    worker_job_timeout_seconds: Annotated[int, Field(ge=1)] = 300

    # ------------------------------------------------------------ pagination --
    default_page_size: Annotated[int, Field(ge=1, le=200)] = 25
    max_page_size: Annotated[int, Field(ge=1, le=500)] = 100

    # ------------------------------------------------------------- domain ---
    #: MVP business rule: only FREE publishers may enter a submission workflow.
    free_only_enforced: bool = True

    # ----------------------------------------------------------- validators --

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        """Accept either a JSON array or a comma-separated string.

        Both forms are supported because both are a reasonable first guess:
        pydantic-settings normally decodes JSON for complex types, while
        ``.env`` files are usually written as plain comma-separated lists.
        These fields are ``NoDecode``, so nothing parses the JSON form for us
        — this validator has to, and previously returned the raw string,
        which then failed as "Input should be a valid list" and stopped the
        application from starting at all.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("{"):
            # Certainly a mistake, and the comma-split below would otherwise
            # turn it into a nonsense one-element list rather than complaining.
            raise ValueError("expected a JSON array of strings, not an object")
        if stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "expected a JSON array of strings or a comma-separated list, "
                    f"got invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(decoded, list):
                raise ValueError("expected a JSON array of strings")
            return [str(item).strip() for item in decoded if str(item).strip()]
        return [item.strip() for item in stripped.split(",") if item.strip()]

    @field_validator("database_url", "database_migration_url")
    @classmethod
    def _require_postgres(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(
            ("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg://")
        ):
            raise ValueError("database URL must be a PostgreSQL URL")
        return value

    @field_validator("encryption_key")
    @classmethod
    def _validate_master_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:  # pragma: no cover - config error
            raise ValueError("ENCRYPTION_KEY must be base64-encoded") from exc
        if len(decoded) != MASTER_KEY_BYTES:
            raise ValueError(
                f"ENCRYPTION_KEY must decode to exactly {MASTER_KEY_BYTES} bytes "
                f"(got {len(decoded)})"
            )
        return value

    @model_validator(mode="after")
    def _validate_page_sizes(self) -> Self:
        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size cannot exceed max_page_size")
        return self

    @model_validator(mode="after")
    def validate_production_hardening(self) -> Self:
        """Refuse to boot a non-local environment with development placeholders."""
        if self.app_env in ("local", "test"):
            return self

        problems: list[str] = []
        if self.jwt_secret.get_secret_value() in _DEV_PLACEHOLDERS:
            problems.append("JWT_SECRET is a development placeholder")
        if len(self.jwt_secret.get_secret_value()) < 32:
            problems.append("JWT_SECRET must be at least 32 characters")
        if self.encryption_key.get_secret_value() in _DEV_PLACEHOLDERS:
            problems.append("ENCRYPTION_KEY is a development placeholder")
        if self.debug:
            problems.append("DEBUG must be false outside local/test")
        if self.log_request_body:
            problems.append("LOG_REQUEST_BODY must be false outside local/test")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not be '*' outside local/test")
        if problems:
            raise ValueError(
                f"insecure configuration for APP_ENV={self.app_env}: " + "; ".join(problems)
            )
        return self

    # -------------------------------------------------------------- helpers --

    @property
    def alembic_url(self) -> str:
        """URL Alembic should use (may be a more privileged role)."""
        return self.database_migration_url or self.database_url

    @property
    def is_production(self) -> bool:
        return self.app_env in ("staging", "production")

    @property
    def master_key(self) -> bytes:
        """Decoded master key (KEK) bytes."""
        return base64.b64decode(self.encryption_key.get_secret_value(), validate=True)

    def sync_database_url(self, url: str | None = None) -> str:
        """Convert an async URL to the psycopg-free sync form used by tooling."""
        target = url or self.alembic_url
        return target.replace("+asyncpg", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

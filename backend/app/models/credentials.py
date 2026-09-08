"""BYOK credentials and per-tenant AI provider configuration."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AiPurpose, CredentialProviderType, CredentialStatus
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Credential(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """A tenant's own provider secret, envelope-encrypted at rest.

    There is no plaintext column and no API that returns one. The row holds
    the ciphertext, its nonce, the wrapped data-encryption key, that key's
    nonce, and the master-key version used to wrap it. ``masked_hint`` is the
    only human-readable trace (``sk-****abcd``) and is generated at write time.

    The AAD used for encryption binds the ciphertext to ``tenant_id``, ``id``
    and ``provider``, so a row copied to another tenant fails to decrypt rather
    than silently working.
    """

    __tablename__ = "credentials"
    __table_args__ = (
        # Idempotency: creating "the OpenAI key called Production" twice is a
        # conflict, not a duplicate row.
        UniqueConstraint(
            "tenant_id", "provider", "label", name="uq_credentials_tenant_provider_label"
        ),
        CheckConstraint(
            CredentialProviderType.check_constraint("provider_type"), name="provider_type_valid"
        ),
        CheckConstraint(CredentialStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint("key_version >= 1", name="key_version_positive"),
        CheckConstraint("octet_length(ciphertext) > 0", name="ciphertext_not_empty"),
        CheckConstraint("octet_length(nonce) = 12", name="nonce_length"),
        CheckConstraint("octet_length(dek_nonce) = 12", name="dek_nonce_length"),
        Index("ix_credentials_tenant_id_provider", "tenant_id", "provider"),
        Index("ix_credentials_tenant_id_status", "tenant_id", "status"),
        {"comment": "Tenant-owned encrypted provider credentials. Never returned in plaintext."},
    )

    #: Provider key, e.g. ``openai``, ``anthropic``, ``serpapi``.
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{CredentialProviderType.AI.value}'")
    )
    #: Human label so a tenant can hold several keys per provider.
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{CredentialStatus.CONFIGURED.value}'")
    )
    #: Display-only fingerprint, e.g. ``sk-****abcd``. Short secrets are fully
    #: masked rather than partially revealed.
    masked_hint: Mapped[str] = mapped_column(String(64), nullable=False)

    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dek_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    #: Non-secret provider settings (base URL for a self-hosted endpoint,
    #: organisation id). Validated to exclude secret-shaped keys on write.
    provider_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantAiConfig(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """Which provider, model and credential a tenant uses for a given purpose.

    Business code asks for a *purpose* ("content_generation"), so switching a
    tenant from OpenAI to Anthropic is a row update — no code change, no
    redeploy, and no vendor name anywhere outside ``app/integrations``.
    """

    __tablename__ = "tenant_ai_configs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "purpose", "provider", name="uq_tenant_ai_configs_tenant_purpose_provider"
        ),
        # Exactly one default per purpose per tenant.
        Index(
            "uq_tenant_ai_configs_tenant_id_purpose_default",
            "tenant_id",
            "purpose",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        CheckConstraint(AiPurpose.check_constraint("purpose"), name="purpose_valid"),
        Index("ix_tenant_ai_configs_tenant_id_purpose", "tenant_id", "purpose"),
        {"comment": "Tenant-owned AI provider selection, by purpose."},
    )

    purpose: Mapped[str] = mapped_column(String(48), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    #: RESTRICT, not CASCADE: deleting a credential that a configuration still
    #: points at must fail loudly rather than silently disable generation.
    credential_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("credentials.id", ondelete="RESTRICT")
    )
    #: Generation parameters (temperature, max_tokens). Non-secret.
    parameters: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

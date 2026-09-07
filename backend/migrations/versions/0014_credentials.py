"""BYOK credentials and per-tenant AI provider configuration.

There is no plaintext column for a secret anywhere in this table, and no
migration ever creates one. The row stores the AES-256-GCM ciphertext, its
nonce, the wrapped data-encryption key, that key's nonce, and the master-key
version used to wrap it. Nonce lengths are checked so a malformed write fails
at the database rather than producing an undecryptable row.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDER_TYPES = "'AI', 'SEARCH', 'SEO_METRICS', 'WEBSITE_INTELLIGENCE', 'OTHER'"
_CREDENTIAL_STATUSES = "'CONFIGURED', 'VERIFIED', 'INVALID', 'DISABLED'"
_AI_PURPOSES = "'content_generation', 'discovery', 'qualification', 'embedding'"


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column(
            "provider_type", sa.String(length=32), server_default=sa.text("'AI'"), nullable=False
        ),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'CONFIGURED'"), nullable=False
        ),
        # Display-only fingerprint such as 'sk-****abcd'.
        sa.Column("masked_hint", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_dek", sa.LargeBinary(), nullable=False),
        sa.Column("dek_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_credentials"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_credentials_tenant_id", ondelete="CASCADE"
        ),
        # Idempotency: "the OpenAI key called Production" exists once.
        sa.UniqueConstraint(
            "tenant_id", "provider", "label", name="uq_credentials_tenant_provider_label"
        ),
        sa.CheckConstraint(
            f"provider_type IN ({_PROVIDER_TYPES})", name="ck_credentials_provider_type_valid"
        ),
        sa.CheckConstraint(
            f"status IN ({_CREDENTIAL_STATUSES})", name="ck_credentials_status_valid"
        ),
        sa.CheckConstraint("key_version >= 1", name="ck_credentials_key_version_positive"),
        sa.CheckConstraint(
            "octet_length(ciphertext) > 0", name="ck_credentials_ciphertext_not_empty"
        ),
        # AES-GCM standard nonce size.
        sa.CheckConstraint("octet_length(nonce) = 12", name="ck_credentials_nonce_length"),
        sa.CheckConstraint("octet_length(dek_nonce) = 12", name="ck_credentials_dek_nonce_length"),
        comment="Tenant-owned encrypted provider credentials. Never returned in plaintext.",
    )
    op.create_index("ix_credentials_tenant_id", "credentials", ["tenant_id"])
    op.create_index("ix_credentials_tenant_id_provider", "credentials", ["tenant_id", "provider"])
    op.create_index("ix_credentials_tenant_id_status", "credentials", ["tenant_id", "status"])
    op.execute(
        "CREATE TRIGGER trg_credentials_updated_at BEFORE UPDATE ON credentials "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "tenant_ai_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=48), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "parameters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_ai_configs"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_tenant_ai_configs_tenant_id", ondelete="CASCADE"
        ),
        # RESTRICT: deleting a credential a configuration still points at must
        # fail loudly rather than silently disabling generation for the tenant.
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["credentials.id"],
            name="fk_tenant_ai_configs_credential_id_credentials",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "purpose", "provider", name="uq_tenant_ai_configs_tenant_purpose_provider"
        ),
        sa.CheckConstraint(
            f"purpose IN ({_AI_PURPOSES})", name="ck_tenant_ai_configs_purpose_valid"
        ),
        comment="Tenant-owned AI provider selection, by purpose.",
    )
    op.create_index("ix_tenant_ai_configs_tenant_id", "tenant_ai_configs", ["tenant_id"])
    op.create_index(
        "ix_tenant_ai_configs_tenant_id_purpose", "tenant_ai_configs", ["tenant_id", "purpose"]
    )
    # Exactly one default provider per purpose per tenant.
    op.create_index(
        "uq_tenant_ai_configs_tenant_id_purpose_default",
        "tenant_ai_configs",
        ["tenant_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.execute(
        "CREATE TRIGGER trg_tenant_ai_configs_updated_at BEFORE UPDATE ON tenant_ai_configs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tenant_ai_configs_updated_at ON tenant_ai_configs")
    for index in (
        "uq_tenant_ai_configs_tenant_id_purpose_default",
        "ix_tenant_ai_configs_tenant_id_purpose",
        "ix_tenant_ai_configs_tenant_id",
    ):
        op.drop_index(index, table_name="tenant_ai_configs")
    op.drop_table("tenant_ai_configs")

    op.execute("DROP TRIGGER IF EXISTS trg_credentials_updated_at ON credentials")
    for index in (
        "ix_credentials_tenant_id_status",
        "ix_credentials_tenant_id_provider",
        "ix_credentials_tenant_id",
    ):
        op.drop_index(index, table_name="credentials")
    op.drop_table("credentials")

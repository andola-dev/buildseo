"""BYOK credential and AI configuration schemas.

The central rule of this module: **no response schema has a field capable of
carrying a secret.** ``CredentialRead`` lists exactly what a caller may see,
and there is no endpoint anywhere that returns a decrypted value. Enforcement
is structural — the field does not exist — rather than a matter of remembering
to exclude it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator, model_validator

from app.config.logging import SENSITIVE_KEY_PARTS
from app.core.enums import AiProvider, AiPurpose, CredentialProviderType, CredentialStatus
from app.schemas.common import ReadSchemaBase, SchemaBase

ProviderKey = Annotated[
    str, StringConstraints(min_length=2, max_length=64, to_lower=True, pattern=r"^[a-z0-9_\-]+$")
]
Label = Annotated[str, StringConstraints(min_length=1, max_length=120)]


def _reject_secret_shaped_keys(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Refuse metadata that looks like it is smuggling a secret.

    ``metadata`` is stored unencrypted and returned by the API, so a caller
    putting ``{"api_key": "..."}`` there would defeat the encryption entirely.
    The same key list drives log redaction.
    """
    if not value:
        return value
    offending = [key for key in value if any(part in key.lower() for part in SENSITIVE_KEY_PARTS)]
    if offending:
        raise ValueError(
            "metadata must not contain secret-like keys "
            f"({', '.join(sorted(offending))}); put the secret in 'secret' instead, "
            "where it is encrypted at rest"
        )
    return value


class CredentialCreate(SchemaBase):
    """Store a provider API key for this tenant.

    The secret is encrypted with a per-credential data key before it is
    written, and is never readable through the API afterwards. Replacing it
    means calling PATCH with a new ``secret``.
    """

    provider: ProviderKey = Field(
        description="Provider key, e.g. openai, anthropic, gemini, openrouter, serpapi"
    )
    provider_type: CredentialProviderType = Field(default=CredentialProviderType.AI)
    label: Label = Field(description="Human label, so a tenant can hold several keys per provider")
    secret: SecretStr = Field(
        min_length=8,
        max_length=8192,
        description="The API key. Encrypted at rest; never returned by any endpoint.",
    )
    provider_metadata: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
        description="Non-secret settings such as a base URL or organisation id",
    )
    verify: bool = Field(
        default=False,
        description="Make a minimal live call to confirm the key works before saving its status",
    )

    @field_validator("provider_metadata")
    @classmethod
    def _no_secrets_in_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_shaped_keys(value) or {}

    @field_validator("secret")
    @classmethod
    def _not_placeholder(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not raw:
            raise ValueError("secret must not be blank")
        if raw.lower() in {"string", "changeme", "your-api-key", "test", "xxx"}:
            raise ValueError("secret looks like a placeholder")
        return SecretStr(raw)


class CredentialUpdate(SchemaBase):
    """Rotate or disable a credential."""

    label: Label | None = None
    secret: SecretStr | None = Field(
        default=None, min_length=8, max_length=8192, description="Replaces the stored key"
    )
    status: CredentialStatus | None = Field(
        default=None, description="Use DISABLED to retire a key without deleting it"
    )
    provider_metadata: dict[str, Any] | None = Field(default=None, alias="metadata")
    verify: bool = Field(default=False)

    @field_validator("provider_metadata")
    @classmethod
    def _no_secrets_in_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _reject_secret_shaped_keys(value)


class CredentialRead(ReadSchemaBase):
    """Credential metadata. Deliberately incapable of carrying the secret.

    There is no ``secret``, ``ciphertext``, ``encrypted_dek`` or ``nonce``
    field here, and no endpoint that reveals one.
    """

    id: UUID
    provider: str
    provider_type: str
    label: str
    status: str = Field(description="CONFIGURED, VERIFIED, INVALID or DISABLED")
    masked_key: str = Field(
        validation_alias="masked_hint",
        description="Display-only fingerprint such as 'sk-****abcd'. Short keys are fully masked.",
    )
    provider_metadata: dict[str, Any] = Field(
        default_factory=dict, serialization_alias="metadata", description="Non-secret settings"
    )
    key_version: int = Field(description="Master-key version the secret is wrapped with")
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CredentialVerifyResult(ReadSchemaBase):
    """Outcome of a live check against the provider."""

    credential_id: UUID
    provider: str
    status: str
    verified: bool
    #: A failure *class*, never the provider's response body, which can echo
    #: the submitted key back.
    error_code: str | None = None
    checked_at: datetime


class AiConfigUpsert(SchemaBase):
    """Choose the provider, model and credential for one purpose."""

    purpose: AiPurpose
    provider: AiProvider
    model: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    credential_id: UUID | None = Field(
        default=None,
        description=(
            "Credential to use. Required for every provider except a self-hosted "
            "'custom' endpoint that needs no key."
        ),
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-secret generation parameters (temperature, max_tokens)",
    )
    is_default: bool = Field(
        default=True, description="Make this the provider used for the purpose"
    )

    @field_validator("parameters")
    @classmethod
    def _no_secrets_in_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_shaped_keys(value) or {}

    @model_validator(mode="after")
    def _credential_required(self) -> Self:
        if self.credential_id is None and self.provider is not AiProvider.CUSTOM:
            raise ValueError(f"credential_id is required for provider '{self.provider.value}'")
        return self


class AiConfigRead(ReadSchemaBase):
    id: UUID
    purpose: str
    provider: str
    model: str
    credential_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_default: bool
    created_at: datetime
    updated_at: datetime

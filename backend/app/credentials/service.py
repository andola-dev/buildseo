"""BYOK credential management.

The one component permitted to see a plaintext provider secret, and only
inside :meth:`CredentialService.resolve_secret`. Everything else — schemas,
routers, audit records, logs — deals in metadata.

Storage: AES-256-GCM under a per-credential data key, itself wrapped by the
deployment's master key. The AAD binds each ciphertext to its tenant, row id
and provider, so a ciphertext copied to another row or another tenant fails
authentication instead of decrypting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.crypto.envelope import (
    EncryptedPayload,
    EnvelopeEncryptionService,
    build_credential_aad,
)
from app.core.domains import mask_secret
from app.core.enums import CredentialStatus
from app.core.exceptions import (
    BusinessRuleError,
    CredentialNotConfiguredError,
    DuplicateResourceError,
)
from app.core.ids import uuid7
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.models.credentials import Credential
from app.repositories.credentials import CredentialRepository, TenantAiConfigRepository
from app.schemas.credentials import CredentialCreate, CredentialUpdate

logger = get_logger(__name__)


class CredentialService:
    """Stores, rotates and resolves tenant provider credentials."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        credentials: CredentialRepository,
        ai_configs: TenantAiConfigRepository,
        encryption: EnvelopeEncryptionService,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._credentials = credentials
        self._ai_configs = ai_configs
        self._encryption = encryption
        self._audit = audit

    # -------------------------------------------------------------- create --

    async def create(self, payload: CredentialCreate) -> Credential:
        """Encrypt and store a new provider secret."""
        provider = payload.provider
        if await self._credentials.get_by_provider_and_label(
            provider=provider, label=payload.label
        ):
            raise DuplicateResourceError(
                f"A '{provider}' credential labelled '{payload.label}' already exists",
                code="CREDENTIAL_EXISTS",
            )

        secret = payload.secret.get_secret_value()
        # The row id is generated before the insert because it is part of the
        # AAD: the ciphertext is bound to the row it will live in.
        credential_id = uuid7()
        aad = build_credential_aad(self._credentials.tenant_id, credential_id, provider)
        sealed = self._encryption.encrypt(secret, aad=aad)

        credential = self._credentials.new(
            id=credential_id,
            provider=provider,
            provider_type=payload.provider_type.value,
            label=payload.label,
            status=CredentialStatus.CONFIGURED.value,
            masked_hint=mask_secret(secret),
            ciphertext=sealed.ciphertext,
            nonce=sealed.nonce,
            encrypted_dek=sealed.encrypted_dek,
            dek_nonce=sealed.dek_nonce,
            key_version=sealed.key_version,
            provider_metadata=payload.provider_metadata,
        )
        await self._credentials.flush()

        await self._audit.record(
            AuditAction.CREDENTIAL_CREATED,
            resource_type="credential",
            resource_id=credential.id,
            metadata={
                "provider": provider,
                "provider_type": payload.provider_type.value,
                "label": payload.label,
            },
        )
        logger.info(
            "credential stored",
            extra={"provider": provider, "credential_id": str(credential.id)},
        )
        return credential

    # ----------------------------------------------------------- retrieval --

    async def get(self, credential_id: UUID) -> Credential:
        return await self._credentials.get_or_raise(credential_id, resource="credential")

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        provider: str | None = None,
        provider_type: str | None = None,
        status: str | None = None,
    ) -> Page[Credential]:
        filters = self._credentials.build_filters(
            provider=provider, provider_type=provider_type, status=status
        )
        return await self._credentials.list_page(page=page, sort=sort, filters=filters)

    # -------------------------------------------------------------- update --

    async def update(self, credential_id: UUID, payload: CredentialUpdate) -> Credential:
        """Rename, rotate or disable a credential."""
        credential = await self.get(credential_id)
        changed: list[str] = []

        if payload.label is not None and payload.label != credential.label:
            if await self._credentials.get_by_provider_and_label(
                provider=credential.provider, label=payload.label
            ):
                raise DuplicateResourceError(
                    f"A '{credential.provider}' credential labelled "
                    f"'{payload.label}' already exists",
                    code="CREDENTIAL_EXISTS",
                )
            credential.label = payload.label
            changed.append("label")

        if payload.secret is not None:
            self._reseal(credential, payload.secret.get_secret_value())
            changed.append("secret")

        if payload.status is not None and payload.status.value != credential.status:
            credential.status = payload.status.value
            changed.append("status")
        if payload.provider_metadata is not None:
            credential.provider_metadata = payload.provider_metadata
            changed.append("metadata")

        await self._credentials.flush()
        action = (
            AuditAction.CREDENTIAL_ROTATED
            if "secret" in changed
            else AuditAction.CREDENTIAL_UPDATED
        )
        await self._audit.record(
            action,
            resource_type="credential",
            resource_id=credential.id,
            metadata={
                "provider": credential.provider,
                "label": credential.label,
                "changed_fields": changed,
                "status": credential.status,
                "key_version": credential.key_version,
            },
        )
        return credential

    def _reseal(self, credential: Credential, secret: str) -> None:
        """Replace the stored secret, re-deriving the AAD for this row."""
        aad = build_credential_aad(credential.tenant_id, credential.id, credential.provider)
        sealed = self._encryption.encrypt(secret, aad=aad)
        credential.ciphertext = sealed.ciphertext
        credential.nonce = sealed.nonce
        credential.encrypted_dek = sealed.encrypted_dek
        credential.dek_nonce = sealed.dek_nonce
        credential.key_version = sealed.key_version
        credential.masked_hint = mask_secret(secret)
        # A rotated key is unproven until it is used or verified again.
        credential.status = CredentialStatus.CONFIGURED.value
        credential.last_verified_at = None

    # -------------------------------------------------------------- delete --

    async def delete(self, credential_id: UUID) -> None:
        """Delete a credential, refusing while an AI configuration uses it."""
        credential = await self.get(credential_id)
        if await self._ai_configs.uses_credential(credential_id):
            # The database FK is RESTRICT; checking here turns a raw constraint
            # error into an explanation the caller can act on.
            raise BusinessRuleError(
                "This credential is still referenced by an AI configuration. "
                "Point that configuration at another credential first.",
                code="CREDENTIAL_IN_USE",
            )

        provider, label = credential.provider, credential.label
        await self._credentials.delete(credential)
        await self._credentials.flush()
        await self._audit.record(
            AuditAction.CREDENTIAL_DELETED,
            resource_type="credential",
            resource_id=credential_id,
            metadata={"provider": provider, "label": label},
        )

    # ------------------------------------------------------------- resolve --

    def resolve_secret(self, credential: Credential) -> str:
        """Decrypt a stored secret.

        The only path from ciphertext to plaintext in the application. The
        result is passed straight into a provider client and must never be
        logged, returned, or written anywhere.
        """
        aad = build_credential_aad(credential.tenant_id, credential.id, credential.provider)
        payload = EncryptedPayload(
            ciphertext=credential.ciphertext,
            nonce=credential.nonce,
            encrypted_dek=credential.encrypted_dek,
            dek_nonce=credential.dek_nonce,
            key_version=credential.key_version,
        )
        return self._encryption.decrypt(payload, aad=aad)

    async def resolve_for_provider(self, provider: str) -> tuple[Credential, str]:
        """Find and decrypt the usable credential for ``provider``."""
        credential = await self._credentials.get_usable_for_provider(provider)
        if credential is None:
            raise CredentialNotConfiguredError(
                f"No usable '{provider}' credential is configured for this workspace. "
                "Add one with POST /api/v1/credentials.",
                details={"provider": provider},
            )
        return credential, self.resolve_secret(credential)

    async def get_secret_for_credential(self, credential_id: UUID) -> tuple[Credential, str]:
        credential = await self.get(credential_id)
        if credential.status == CredentialStatus.DISABLED.value:
            raise CredentialNotConfiguredError(
                "That credential is disabled",
                code="CREDENTIAL_DISABLED",
                details={"credential_id": str(credential_id)},
            )
        return credential, self.resolve_secret(credential)

    # -------------------------------------------------------------- status --

    async def mark_verification(
        self, credential: Credential, *, verified: bool, error_code: str | None = None
    ) -> Credential:
        """Record the outcome of a live check against the provider.

        Marking a rejected key INVALID stops every later request retrying it,
        which is both faster and avoids hammering the provider with a key it
        has already refused.
        """
        credential.status = (
            CredentialStatus.VERIFIED.value if verified else CredentialStatus.INVALID.value
        )
        if verified:
            credential.last_verified_at = datetime.now(UTC)
        await self._credentials.flush()
        await self._audit.record(
            AuditAction.CREDENTIAL_VERIFIED,
            resource_type="credential",
            resource_id=credential.id,
            metadata={
                "provider": credential.provider,
                "label": credential.label,
                "verified": verified,
                "error_code": error_code,
            },
        )
        return credential

    @staticmethod
    def metadata_base_url(credential: Credential) -> str:
        """Read a self-hosted endpoint URL from a credential's metadata."""
        raw: Any = credential.provider_metadata.get("base_url", "")
        return str(raw) if raw else ""

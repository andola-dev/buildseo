"""BYOK credential and AI-configuration data access.

Nothing in this module decrypts anything. Repositories return rows;
``CredentialService`` is the only component that can turn a row into a
plaintext secret, and it never hands one to a schema.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import CredentialStatus
from app.models.credentials import Credential, TenantAiConfig
from app.repositories.base import TenantRepository


class CredentialRepository(TenantRepository[Credential]):
    model = Credential
    sortable_fields = frozenset({"created_at", "updated_at", "provider", "label", "status"})
    default_sort = "created_at"

    async def get_by_provider_and_label(self, *, provider: str, label: str) -> Credential | None:
        """Idempotency lookup matching ``uq_credentials_tenant_provider_label``."""
        result = await self.session.execute(
            self._select().where(Credential.provider == provider, Credential.label == label)
        )
        return result.scalar_one_or_none()

    async def get_usable_for_provider(self, provider: str) -> Credential | None:
        """The credential a provider client should use.

        Prefers one already verified against the provider, then any merely
        configured one; disabled and known-invalid credentials are excluded so
        a broken key is not retried on every request.
        """
        result = await self.session.execute(
            self._select()
            .where(
                Credential.provider == provider,
                Credential.status.in_(
                    [CredentialStatus.VERIFIED.value, CredentialStatus.CONFIGURED.value]
                ),
            )
            .order_by(
                # VERIFIED sorts before CONFIGURED alphabetically only by
                # accident, so order explicitly on the verification timestamp.
                Credential.last_verified_at.desc().nullslast(),
                Credential.created_at.desc(),
            )
        )
        return result.scalars().first()

    def build_filters(
        self,
        *,
        provider: str | None = None,
        provider_type: str | None = None,
        status: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if provider:
            filters.append(Credential.provider == provider)
        if provider_type:
            filters.append(Credential.provider_type == provider_type)
        if status:
            filters.append(Credential.status == status)
        return filters


class TenantAiConfigRepository(TenantRepository[TenantAiConfig]):
    model = TenantAiConfig
    sortable_fields = frozenset({"created_at", "updated_at", "purpose", "provider"})
    default_sort = "purpose"

    async def get_default_for_purpose(self, purpose: str) -> TenantAiConfig | None:
        """The provider a tenant has chosen for a purpose.

        This is the whole point of the abstraction: business code asks for
        ``content_generation`` and never names a vendor.
        """
        result = await self.session.execute(
            self._select().where(
                TenantAiConfig.purpose == purpose, TenantAiConfig.is_default.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def get_for_purpose_and_provider(
        self, *, purpose: str, provider: str
    ) -> TenantAiConfig | None:
        result = await self.session.execute(
            self._select().where(
                TenantAiConfig.purpose == purpose, TenantAiConfig.provider == provider
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[TenantAiConfig]:
        result = await self.session.execute(
            self._select().order_by(TenantAiConfig.purpose, TenantAiConfig.provider)
        )
        return list(result.scalars().all())

    async def clear_default_for_purpose(self, purpose: str) -> None:
        """Drop the current default so a new one can be set.

        Required because ``uq_tenant_ai_configs_tenant_id_purpose_default`` is
        a partial unique index: two defaults for one purpose cannot coexist
        even momentarily within a transaction's constraint check.
        """
        result = await self.session.execute(
            select(TenantAiConfig).where(
                TenantAiConfig.tenant_id == self.tenant_id,
                TenantAiConfig.purpose == purpose,
                TenantAiConfig.is_default.is_(True),
            )
        )
        for config in result.scalars().all():
            config.is_default = False
        await self.session.flush()

    async def uses_credential(self, credential_id: UUID) -> bool:
        """Whether any configuration still points at a credential."""
        return await self.exists([TenantAiConfig.credential_id == credential_id])

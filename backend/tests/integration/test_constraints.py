"""Database-level invariants.

Every rule asserted here is *also* checked in the service layer. That is the
point: the decision order is Security → Tenant Isolation → Correctness, and a
rule this central to the product should not depend on application code being
free of bugs. If a future refactor drops a service check, these tests keep
failing until the database is asked to stop caring too.

Each test opens its own session because a constraint violation aborts the
transaction it happens in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.enums import (
    AiPurpose,
    CredentialProviderType,
    CredentialStatus,
    OpportunityStatus,
    OpportunityType,
    PricingType,
    PublisherCategory,
    PublisherStatus,
    SubmissionMethod,
    SubmissionStatus,
)
from app.db.session import TenantAwareSession
from app.repositories.credentials import CredentialRepository, TenantAiConfigRepository
from app.repositories.idempotency import IdempotencyKeyRepository
from app.repositories.jobs import JobRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.publishers import PublisherRepository
from app.repositories.submissions import SubmissionRepository
from tests.fixtures.tenants import TenantFixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# Not a real key: 32 zero bytes standing in for ciphertext the crypto layer
# would produce. Nothing here exercises encryption.
FAKE_CIPHERTEXT = b"\x00" * 32
FAKE_NONCE = b"\x00" * 12


async def _bound(
    factory: async_sessionmaker[TenantAwareSession], fixture: TenantFixture
) -> TenantAwareSession:
    session = factory()
    await session.set_tenant_context(tenant_id=fixture.tenant_id, user_id=fixture.owner.id)
    return session


def _publisher_values(slug: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "domain": f"{slug}.test",
        "normalized_domain": f"{slug}.test",
        "website_url": f"https://{slug}.test",
        "name": slug,
        "category": PublisherCategory.BUSINESS_DIRECTORY.value,
        "submission_method": SubmissionMethod.MANUAL.value,
        "pricing_type": PricingType.FREE.value,
        "status": PublisherStatus.QUALIFIED.value,
    }
    values.update(overrides)
    return values


class TestUniqueConstraints:
    async def test_a_publisher_domain_is_unique_within_a_tenant(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = PublisherRepository(session)
            repository.new(
                **_publisher_values(
                    "dupe", normalized_domain=tenant_a.free_publisher.normalized_domain
                )
            )
            with pytest.raises(IntegrityError, match="uq_publishers_tenant_id_normalized_domain"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_the_same_domain_may_exist_in_two_tenants(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        tenant_b: TenantFixture,
    ) -> None:
        """De-duplication is per workspace: two customers may both list Yelp."""
        session = await _bound(session_factory, tenant_b)
        try:
            repository = PublisherRepository(session)
            publisher = repository.new(
                **_publisher_values(
                    "shared", normalized_domain=tenant_a.free_publisher.normalized_domain
                )
            )
            await repository.flush()
            assert publisher.tenant_id == tenant_b.tenant_id
        finally:
            await session.rollback()
            await session.close()

    async def test_an_opportunity_is_unique_per_campaign_publisher_and_target(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """The natural key behind idempotent opportunity creation."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = OpportunityRepository(session)
            repository.new(
                campaign_id=tenant_a.campaign.id,
                publisher_id=tenant_a.free_publisher.id,
                opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
                target_url=tenant_a.opportunity.target_url,
                status=OpportunityStatus.DISCOVERED.value,
            )
            with pytest.raises(
                IntegrityError, match="uq_opportunities_tenant_campaign_publisher_target"
            ):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_a_credential_label_is_unique_per_provider(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = CredentialRepository(session)
            for _ in range(2):
                repository.new(
                    provider="anthropic",
                    provider_type=CredentialProviderType.AI.value,
                    label="primary",
                    status=CredentialStatus.CONFIGURED.value,
                    masked_hint="sk-****",
                    ciphertext=FAKE_CIPHERTEXT,
                    nonce=FAKE_NONCE,
                    encrypted_dek=FAKE_CIPHERTEXT,
                    dek_nonce=FAKE_NONCE,
                )
            with pytest.raises(IntegrityError, match="uq_credentials_tenant_provider_label"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_a_job_idempotency_key_is_unique_per_tenant(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = JobRepository(session)
            for _ in range(2):
                repository.new(
                    task_name="publisher.qualify",
                    payload={"publisher_id": str(tenant_a.free_publisher.id)},
                    idempotency_key="qualify-once",
                )
            with pytest.raises(IntegrityError, match="uq_jobs_tenant_idempotency_key"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_an_idempotency_key_is_unique_per_endpoint(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = IdempotencyKeyRepository(session)
            for _ in range(2):
                repository.new(
                    key="client-supplied-key",
                    endpoint="POST /api/v1/opportunities",
                    request_hash="a" * 64,
                )
            with pytest.raises(IntegrityError):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_the_same_key_may_be_reused_on_a_different_endpoint(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Keys are scoped to an endpoint, so a client's UUID generator is free."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = IdempotencyKeyRepository(session)
            for endpoint in ("POST /api/v1/opportunities", "POST /api/v1/submissions"):
                repository.new(
                    key="client-supplied-key",
                    endpoint=endpoint,
                    request_hash="b" * 64,
                )
            await repository.flush()
            assert await repository.get("client-supplied-key", "POST /api/v1/submissions")
        finally:
            await session.rollback()
            await session.close()


class TestPartialUniqueIndexes:
    async def test_only_one_live_submission_per_opportunity(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = SubmissionRepository(session)
            for _ in range(2):
                repository.new(
                    campaign_id=tenant_a.campaign.id,
                    opportunity_id=tenant_a.opportunity.id,
                    target_url=tenant_a.opportunity.target_url,
                    submission_method=SubmissionMethod.MANUAL.value,
                    status=SubmissionStatus.READY.value,
                )
            with pytest.raises(
                IntegrityError, match="uq_submissions_tenant_id_opportunity_id_live"
            ):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_terminal_submissions_do_not_occupy_the_slot(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Two rejected attempts plus one live retry is a legitimate history."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = SubmissionRepository(session)
            for status in (
                SubmissionStatus.REJECTED.value,
                SubmissionStatus.FAILED.value,
                SubmissionStatus.READY.value,
            ):
                repository.new(
                    campaign_id=tenant_a.campaign.id,
                    opportunity_id=tenant_a.opportunity.id,
                    target_url=tenant_a.opportunity.target_url,
                    submission_method=SubmissionMethod.MANUAL.value,
                    status=status,
                )
            await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_only_one_default_ai_config_per_purpose(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = TenantAiConfigRepository(session)
            for provider in ("anthropic", "openai"):
                repository.new(
                    purpose=AiPurpose.CONTENT_GENERATION.value,
                    provider=provider,
                    model="a-model",
                    is_default=True,
                )
            with pytest.raises(
                IntegrityError, match="uq_tenant_ai_configs_tenant_id_purpose_default"
            ):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_non_default_configs_may_coexist(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = TenantAiConfigRepository(session)
            repository.new(
                purpose=AiPurpose.CONTENT_GENERATION.value,
                provider="anthropic",
                model="a-model",
                is_default=True,
            )
            repository.new(
                purpose=AiPurpose.CONTENT_GENERATION.value,
                provider="openai",
                model="another-model",
                is_default=False,
            )
            await repository.flush()

            default = await repository.get_default_for_purpose(AiPurpose.CONTENT_GENERATION.value)
            assert default is not None
            assert default.provider == "anthropic"
        finally:
            await session.rollback()
            await session.close()


class TestFreeOnlyIsEnforcedByTheDatabase:
    async def test_a_paid_publisher_cannot_enter_the_submission_workflow(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Business rules 1 and 2, enforced by ``enforce_submission_free_only``.

        The service refuses this too. Both checks exist because paid placement
        is out of scope for the product, not merely unimplemented.
        """
        session = await _bound(session_factory, tenant_a)
        try:
            opportunities = OpportunityRepository(session)
            paid_opportunity = opportunities.new(
                campaign_id=tenant_a.campaign.id,
                publisher_id=tenant_a.paid_publisher.id,
                opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
                target_url="https://tenant-a-client.test/paid",
                status=OpportunityStatus.SELECTED.value,
            )
            await opportunities.flush()

            submissions = SubmissionRepository(session)
            submissions.new(
                campaign_id=tenant_a.campaign.id,
                opportunity_id=paid_opportunity.id,
                target_url="https://tenant-a-client.test/paid",
                submission_method=SubmissionMethod.MANUAL.value,
                status=SubmissionStatus.READY.value,
            )
            with pytest.raises(IntegrityError, match="only FREE publishers"):
                await submissions.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_a_submission_for_an_invisible_opportunity_fails_closed(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """The trigger is not SECURITY DEFINER, so it runs under the caller's RLS.

        An opportunity the caller cannot see is indistinguishable from one that
        does not exist, and the trigger refuses rather than assuming FREE.
        """
        session = await _bound(session_factory, tenant_a)
        try:
            submissions = SubmissionRepository(session)
            submissions.new(
                campaign_id=tenant_a.campaign.id,
                opportunity_id=uuid4(),
                target_url="https://tenant-a-client.test/ghost",
                submission_method=SubmissionMethod.MANUAL.value,
                status=SubmissionStatus.READY.value,
            )
            with pytest.raises(IntegrityError):
                await submissions.flush()
        finally:
            await session.rollback()
            await session.close()


class TestApprovalGateIsEnforcedByTheDatabase:
    @pytest.mark.parametrize(
        "status",
        [
            SubmissionStatus.SUBMITTED.value,
            SubmissionStatus.PUBLISHED.value,
            SubmissionStatus.VERIFICATION_PENDING.value,
            SubmissionStatus.VERIFIED.value,
        ],
    )
    async def test_reaching_submitted_requires_a_recorded_approval(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
        status: str,
    ) -> None:
        """Human-in-the-loop: nothing leaves the workspace unauthorised."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = SubmissionRepository(session)
            repository.new(
                campaign_id=tenant_a.campaign.id,
                opportunity_id=tenant_a.opportunity.id,
                target_url=tenant_a.opportunity.target_url,
                submission_method=SubmissionMethod.MANUAL.value,
                status=status,
            )
            with pytest.raises(IntegrityError, match="submitted_requires_approval"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_an_approved_submission_is_accepted(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = SubmissionRepository(session)
            submission = repository.new(
                campaign_id=tenant_a.campaign.id,
                opportunity_id=tenant_a.opportunity.id,
                target_url=tenant_a.opportunity.target_url,
                submission_method=SubmissionMethod.MANUAL.value,
                status=SubmissionStatus.SUBMITTED.value,
                approved_by_user_id=tenant_a.owner.id,
                approved_at=datetime.now(UTC),
                submitted_at=datetime.now(UTC),
            )
            await repository.flush()
            assert submission.approved_by_user_id == tenant_a.owner.id
        finally:
            await session.rollback()
            await session.close()

    async def test_partial_approval_evidence_is_not_enough(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Both the approver and the timestamp are required, not either one."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = SubmissionRepository(session)
            repository.new(
                campaign_id=tenant_a.campaign.id,
                opportunity_id=tenant_a.opportunity.id,
                target_url=tenant_a.opportunity.target_url,
                submission_method=SubmissionMethod.MANUAL.value,
                status=SubmissionStatus.SUBMITTED.value,
                approved_by_user_id=tenant_a.owner.id,
            )
            with pytest.raises(IntegrityError, match="submitted_requires_approval"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()


class TestCheckConstraints:
    async def test_an_unknown_status_value_is_rejected(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """Enum vocabularies live in the database as well as in Python."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = PublisherRepository(session)
            repository.new(**_publisher_values("bad-status", status="TOTALLY_MADE_UP"))
            with pytest.raises(IntegrityError, match="status_valid"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_an_out_of_range_priority_is_rejected(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        session = await _bound(session_factory, tenant_a)
        try:
            repository = OpportunityRepository(session)
            repository.new(
                campaign_id=tenant_a.campaign.id,
                publisher_id=tenant_a.free_publisher.id,
                opportunity_type=OpportunityType.FREE_DIRECTORY_LISTING.value,
                target_url="https://tenant-a-client.test/priority",
                status=OpportunityStatus.DISCOVERED.value,
                priority=1000,
            )
            with pytest.raises(IntegrityError, match="priority_range"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_a_credential_nonce_must_be_the_right_length(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """AES-GCM nonces are 12 bytes; a wrong length means a bug upstream."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = CredentialRepository(session)
            repository.new(
                provider="anthropic",
                provider_type=CredentialProviderType.AI.value,
                label="wrong-nonce",
                status=CredentialStatus.CONFIGURED.value,
                masked_hint="sk-****",
                ciphertext=FAKE_CIPHERTEXT,
                nonce=b"\x00" * 8,
                encrypted_dek=FAKE_CIPHERTEXT,
                dek_nonce=FAKE_NONCE,
            )
            with pytest.raises(IntegrityError, match="nonce_length"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

    async def test_a_credential_must_carry_ciphertext(
        self,
        session_factory: async_sessionmaker[TenantAwareSession],
        tenant_a: TenantFixture,
    ) -> None:
        """There is no such thing as a stored plaintext credential."""
        session = await _bound(session_factory, tenant_a)
        try:
            repository = CredentialRepository(session)
            repository.new(
                provider="anthropic",
                provider_type=CredentialProviderType.AI.value,
                label="empty-ciphertext",
                status=CredentialStatus.CONFIGURED.value,
                masked_hint="sk-****",
                ciphertext=b"",
                nonce=FAKE_NONCE,
                encrypted_dek=FAKE_CIPHERTEXT,
                dek_nonce=FAKE_NONCE,
            )
            with pytest.raises(IntegrityError, match="ciphertext_not_empty"):
                await repository.flush()
        finally:
            await session.rollback()
            await session.close()

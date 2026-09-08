"""Builds the service graph for one unit of work.

Every service is constructed per request (or per job) around a single
tenant-scoped session, so all of them share one transaction and one audit
trail. Construction is lazy and memoised: a request that only lists publishers
does not build the AI stack.
"""

from __future__ import annotations

from functools import cached_property

from app.audit.service import AuditService
from app.bootstrap import AppResources
from app.campaigns.service import CampaignService
from app.credentials.service import CredentialService
from app.credentials.verification import CredentialVerificationService
from app.db.session import TenantAwareSession
from app.integrations.ai.factory import AIProviderFactory
from app.integrations.ai.usage import AiUsageService
from app.integrations.crawler.http_crawler import HttpCrawlerProvider
from app.integrations.discovery.registry import DiscoveryProviderRegistry
from app.integrations.metrics.base import MetricsProvider, NullMetricsProvider
from app.integrations.submission.form import FormSubmissionProvider
from app.integrations.submission.manual import ManualSubmissionProvider
from app.opportunities.content import ContentGenerationService
from app.opportunities.service import OpportunityService
from app.organizations.service import ClientWebsiteService
from app.publishers.discovery import DiscoveryService
from app.publishers.qualification import QualificationService
from app.publishers.scoring import ScoringWeights
from app.publishers.service import PublisherService
from app.rbac.service import RbacService
from app.repositories.ai_usage import AiUsageRepository
from app.repositories.audit import AuditLogRepository
from app.repositories.campaigns import CampaignRepository
from app.repositories.client_websites import ClientWebsiteRepository
from app.repositories.credentials import CredentialRepository, TenantAiConfigRepository
from app.repositories.idempotency import IdempotencyKeyRepository
from app.repositories.jobs import JobRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.publishers import DiscoveryRunRepository, PublisherRepository
from app.repositories.rbac import (
    EffectivePermissionRepository,
    MembershipRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.repositories.sessions import RefreshSessionRepository
from app.repositories.submissions import GeneratedContentRepository, SubmissionRepository
from app.repositories.tenants import MembershipRepository, TenantRepositoryGlobal
from app.repositories.users import UserRepository
from app.submissions.service import SubmissionService
from app.submissions.verification import HttpLinkVerifier
from app.tenants.service import TenantService
from app.users.service import UserService
from app.workers.queue import PostgresTaskQueue


class ServiceFactory:
    """Assembles repositories and services around one session.

    ``tenant_settings`` carries the active workspace's ``settings`` JSON so
    tenant-tunable behaviour — currently the scoring weights — reaches the
    services that need it without every caller having to pass it down.
    """

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        resources: AppResources,
        tenant_settings: dict[str, object] | None = None,
        metrics_provider: MetricsProvider | None = None,
    ) -> None:
        self._session = session
        self._resources = resources
        self._tenant_settings = tenant_settings or {}
        self._metrics = metrics_provider or NullMetricsProvider()

    # ------------------------------------------------------- repositories --

    @cached_property
    def users(self) -> UserRepository:
        return UserRepository(self._session)

    @cached_property
    def tenants(self) -> TenantRepositoryGlobal:
        return TenantRepositoryGlobal(self._session)

    @cached_property
    def memberships(self) -> MembershipRepository:
        return MembershipRepository(self._session)

    @cached_property
    def refresh_sessions(self) -> RefreshSessionRepository:
        return RefreshSessionRepository(self._session)

    @cached_property
    def permissions(self) -> PermissionRepository:
        return PermissionRepository(self._session)

    @cached_property
    def roles(self) -> RoleRepository:
        return RoleRepository(self._session)

    @cached_property
    def role_permissions(self) -> RolePermissionRepository:
        return RolePermissionRepository(self._session)

    @cached_property
    def membership_roles(self) -> MembershipRoleRepository:
        return MembershipRoleRepository(self._session)

    @cached_property
    def effective_permissions(self) -> EffectivePermissionRepository:
        return EffectivePermissionRepository(self._session)

    @cached_property
    def client_websites(self) -> ClientWebsiteRepository:
        return ClientWebsiteRepository(self._session)

    @cached_property
    def campaigns(self) -> CampaignRepository:
        return CampaignRepository(self._session)

    @cached_property
    def publishers(self) -> PublisherRepository:
        return PublisherRepository(self._session)

    @cached_property
    def discovery_runs(self) -> DiscoveryRunRepository:
        return DiscoveryRunRepository(self._session)

    @cached_property
    def opportunities(self) -> OpportunityRepository:
        return OpportunityRepository(self._session)

    @cached_property
    def submissions(self) -> SubmissionRepository:
        return SubmissionRepository(self._session)

    @cached_property
    def generated_contents(self) -> GeneratedContentRepository:
        return GeneratedContentRepository(self._session)

    @cached_property
    def credential_repository(self) -> CredentialRepository:
        return CredentialRepository(self._session)

    @cached_property
    def ai_configs(self) -> TenantAiConfigRepository:
        return TenantAiConfigRepository(self._session)

    @cached_property
    def ai_usage_repository(self) -> AiUsageRepository:
        return AiUsageRepository(self._session)

    @cached_property
    def audit_logs(self) -> AuditLogRepository:
        return AuditLogRepository(self._session)

    @cached_property
    def jobs(self) -> JobRepository:
        return JobRepository(self._session)

    @cached_property
    def idempotency_keys(self) -> IdempotencyKeyRepository:
        return IdempotencyKeyRepository(self._session)

    # ------------------------------------------------------------ services --

    @cached_property
    def audit(self) -> AuditService:
        return AuditService(self.audit_logs)

    @cached_property
    def task_queue(self) -> PostgresTaskQueue:
        return PostgresTaskQueue(
            session=self._session,
            jobs=self.jobs,
            audit=self.audit,
            default_max_attempts=self._resources.settings.worker_max_attempts,
        )

    @cached_property
    def tenant_service(self) -> TenantService:
        return TenantService(
            session=self._session,
            tenants=self.tenants,
            memberships=self.memberships,
            users=self.users,
            roles=self.roles,
            role_permissions=self.role_permissions,
            membership_roles=self.membership_roles,
            permissions=self.permissions,
            audit=self.audit,
        )

    @cached_property
    def user_service(self) -> UserService:
        return UserService(
            session=self._session,
            users=self.users,
            memberships=self.memberships,
            tenants=self.tenants,
        )

    @cached_property
    def rbac_service(self) -> RbacService:
        return RbacService(
            session=self._session,
            roles=self.roles,
            permissions=self.permissions,
            role_permissions=self.role_permissions,
            membership_roles=self.membership_roles,
            effective=self.effective_permissions,
            audit=self.audit,
        )

    @cached_property
    def client_website_service(self) -> ClientWebsiteService:
        return ClientWebsiteService(
            session=self._session, repository=self.client_websites, audit=self.audit
        )

    @cached_property
    def campaign_service(self) -> CampaignService:
        return CampaignService(
            session=self._session,
            campaigns=self.campaigns,
            client_websites=self.client_websites,
            opportunities=self.opportunities,
            submissions=self.submissions,
            audit=self.audit,
        )

    @cached_property
    def publisher_service(self) -> PublisherService:
        return PublisherService(session=self._session, publishers=self.publishers, audit=self.audit)

    @cached_property
    def scoring_weights(self) -> ScoringWeights:
        """Weights from the workspace's own settings, defaults otherwise."""
        raw = self._tenant_settings.get("scoring")
        return ScoringWeights.from_mapping(raw if isinstance(raw, dict) else None)

    @cached_property
    def crawler(self) -> HttpCrawlerProvider:
        return HttpCrawlerProvider(client=self._resources.http_client)

    @cached_property
    def qualification_service(self) -> QualificationService:
        return QualificationService(
            session=self._session,
            publishers=self.publishers,
            crawler=self.crawler,
            metrics=self._metrics,
            audit=self.audit,
            weights=self.scoring_weights,
        )

    @cached_property
    def discovery_service(self) -> DiscoveryService:
        return DiscoveryService(
            session=self._session,
            publishers=self.publishers,
            runs=self.discovery_runs,
            audit=self.audit,
        )

    @cached_property
    def credential_service(self) -> CredentialService:
        return CredentialService(
            session=self._session,
            credentials=self.credential_repository,
            ai_configs=self.ai_configs,
            encryption=self._resources.encryption,
            audit=self.audit,
        )

    @cached_property
    def credential_verification_service(self) -> CredentialVerificationService:
        return CredentialVerificationService(
            credentials=self.credential_service,
            http_client=self._resources.http_client,
        )

    @cached_property
    def ai_factory(self) -> AIProviderFactory:
        return AIProviderFactory(
            configs=self.ai_configs,
            credentials=self.credential_service,
            http_client=self._resources.http_client,
        )

    @cached_property
    def ai_usage_service(self) -> AiUsageService:
        return AiUsageService(session=self._session, repository=self.ai_usage_repository)

    @cached_property
    def discovery_registry(self) -> DiscoveryProviderRegistry:
        return DiscoveryProviderRegistry(
            http_client=self._resources.http_client,
            credentials=self.credential_service,
            credential_repository=self.credential_repository,
            ai_factory=self.ai_factory,
        )

    @cached_property
    def opportunity_service(self) -> OpportunityService:
        return OpportunityService(
            session=self._session,
            opportunities=self.opportunities,
            publishers=self.publishers,
            campaigns=self.campaigns,
            audit=self.audit,
        )

    @cached_property
    def content_service(self) -> ContentGenerationService:
        return ContentGenerationService(
            session=self._session,
            contents=self.generated_contents,
            opportunities=self.opportunities,
            campaigns=self.campaigns,
            client_websites=self.client_websites,
            ai_factory=self.ai_factory,
            usage=self.ai_usage_service,
            audit=self.audit,
        )

    @cached_property
    def submission_service(self) -> SubmissionService:
        return SubmissionService(
            session=self._session,
            submissions=self.submissions,
            opportunities=self.opportunities,
            contents=self.generated_contents,
            audit=self.audit,
            manual_provider=ManualSubmissionProvider(),
            # Automatic delivery stays off: the form adapter pre-flights a
            # target and hands it to a human. See app.integrations.submission.form.
            form_provider=FormSubmissionProvider(
                client=self._resources.http_client, allow_automatic_submission=False
            ),
            verifier=HttpLinkVerifier(client=self._resources.http_client),
        )

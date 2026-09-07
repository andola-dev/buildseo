"""Domain enumerations.

Every enum is a ``StrEnum`` stored in a ``text`` column guarded by a CHECK
constraint built from :meth:`DomainEnum.values`. Native PostgreSQL ``ENUM``
types were rejected deliberately: adding a value to one cannot be done in the
same transaction that uses it, and removing one requires recreating the type
and every dependent column. A CHECK constraint is altered by a single, fully
reversible migration statement — which matters for a product that will keep
adding opportunity types, submission methods and publisher categories.
"""

from __future__ import annotations

from enum import StrEnum


class DomainEnum(StrEnum):
    """Base class adding the helpers migrations and schemas need."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def check_constraint(cls, column: str) -> str:
        """Render a SQL ``IN`` predicate for a CHECK constraint."""
        rendered = ", ".join(f"'{value}'" for value in cls.values())
        return f"{column} IN ({rendered})"


# --------------------------------------------------------------------------- #
# Identity and access
# --------------------------------------------------------------------------- #


class TenantStatus(DomainEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class MembershipStatus(DomainEnum):
    """Only ``ACTIVE`` grants access; the others are membership records that
    deliberately do not."""

    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"
    REMOVED = "REMOVED"


class SystemRoleSlug(DomainEnum):
    """Slugs of the roles seeded into every new tenant.

    Authorisation never branches on these — they exist so seeding is
    deterministic and so the UI can label a role. Permission checks always go
    through the role→permission mapping.
    """

    OWNER = "owner"
    ADMIN = "admin"
    SEO_MANAGER = "seo_manager"
    SEO_SPECIALIST = "seo_specialist"
    VIEWER = "viewer"


# --------------------------------------------------------------------------- #
# Client websites and campaigns
# --------------------------------------------------------------------------- #


class ClientWebsiteStatus(DomainEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class CampaignStatus(DomainEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# --------------------------------------------------------------------------- #
# Publishers
# --------------------------------------------------------------------------- #


class PricingType(DomainEnum):
    """Whether a publisher charges for a listing.

    MVP business rule: only ``FREE`` may enter the submission workflow. The
    other values exist so a paid or unknown publisher can be *recorded* during
    research without becoming submittable — enforced in the service layer, by
    a database trigger on the submission path, and by
    :meth:`submittable_values`.
    """

    FREE = "FREE"
    PAID = "PAID"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def submittable_values(cls) -> tuple[str, ...]:
        return (cls.FREE.value,)


class PublisherStatus(DomainEnum):
    DISCOVERED = "DISCOVERED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"


class SubmissionMethod(DomainEnum):
    """How a listing reaches a publisher.

    ``FORM`` is opt-in per publisher and the form adapter refuses any target
    that presents a CAPTCHA or anti-bot challenge, falling back to ``MANUAL``.
    No value here implies bypassing a publisher's controls.
    """

    MANUAL = "MANUAL"
    FORM = "FORM"
    EMAIL = "EMAIL"
    API = "API"
    ACCOUNT_REQUIRED = "ACCOUNT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class LinkType(DomainEnum):
    DOFOLLOW = "DOFOLLOW"
    NOFOLLOW = "NOFOLLOW"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class PublisherCategory(DomainEnum):
    """Legitimate free-listing categories supported by the MVP.

    The list contains only directory and profile listing types. Paid guest
    posts, sponsored articles, link marketplaces, PBNs and comment/forum spam
    are out of scope by design and have no representation here.
    """

    BUSINESS_DIRECTORY = "BUSINESS_DIRECTORY"
    LOCAL_DIRECTORY = "LOCAL_DIRECTORY"
    COMPANY_LISTING = "COMPANY_LISTING"
    STARTUP_DIRECTORY = "STARTUP_DIRECTORY"
    SOFTWARE_DIRECTORY = "SOFTWARE_DIRECTORY"
    INDUSTRY_DIRECTORY = "INDUSTRY_DIRECTORY"
    ORGANIZATION_LISTING = "ORGANIZATION_LISTING"
    PROFILE_LISTING = "PROFILE_LISTING"
    REVIEW_PLATFORM = "REVIEW_PLATFORM"
    EVENT_LISTING = "EVENT_LISTING"
    JOB_BOARD = "JOB_BOARD"
    OTHER = "OTHER"


class DiscoveryRunStatus(DomainEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# --------------------------------------------------------------------------- #
# Opportunities
# --------------------------------------------------------------------------- #


class OpportunityType(DomainEnum):
    FREE_DIRECTORY_LISTING = "FREE_DIRECTORY_LISTING"
    FREE_LOCAL_LISTING = "FREE_LOCAL_LISTING"
    FREE_COMPANY_PROFILE = "FREE_COMPANY_PROFILE"
    FREE_STARTUP_LISTING = "FREE_STARTUP_LISTING"
    FREE_SOFTWARE_LISTING = "FREE_SOFTWARE_LISTING"
    FREE_INDUSTRY_LISTING = "FREE_INDUSTRY_LISTING"
    FREE_ORGANIZATION_LISTING = "FREE_ORGANIZATION_LISTING"
    FREE_PROFILE_LISTING = "FREE_PROFILE_LISTING"


class OpportunityStatus(DomainEnum):
    DISCOVERED = "DISCOVERED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    SELECTED = "SELECTED"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


# --------------------------------------------------------------------------- #
# Submissions
# --------------------------------------------------------------------------- #


class SubmissionStatus(DomainEnum):
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PUBLISHED = "PUBLISHED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"

    @classmethod
    def terminal_values(cls) -> tuple[str, ...]:
        """Statuses after which a retry may create a new submission row."""
        return (cls.REJECTED.value, cls.FAILED.value)


class ContentStatus(DomainEnum):
    """Review state of AI-drafted listing copy.

    Content is always persisted before submission, so a human reviews (and an
    auditor can later inspect) exactly what was sent.
    """

    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


# --------------------------------------------------------------------------- #
# BYOK, AI and operations
# --------------------------------------------------------------------------- #


class CredentialProviderType(DomainEnum):
    AI = "AI"
    SEARCH = "SEARCH"
    SEO_METRICS = "SEO_METRICS"
    WEBSITE_INTELLIGENCE = "WEBSITE_INTELLIGENCE"
    OTHER = "OTHER"


class CredentialStatus(DomainEnum):
    CONFIGURED = "CONFIGURED"
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    DISABLED = "DISABLED"


class AiProvider(DomainEnum):
    """Supported LLM providers. Extending this list adds an adapter, never a
    change to business logic."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"


class AiPurpose(DomainEnum):
    """What a tenant's AI configuration is for.

    Business code asks for a *purpose*, never a vendor, so a tenant can use
    different providers for content generation and embeddings.
    """

    CONTENT_GENERATION = "content_generation"
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    EMBEDDING = "embedding"


class AiOperation(DomainEnum):
    GENERATE = "generate"
    EMBED = "embed"


class AiUsageStatus(DomainEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobStatus(DomainEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

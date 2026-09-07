"""Publisher, discovery and qualification schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from app.core.domains import normalize_url
from app.core.enums import (
    LinkType,
    PricingType,
    PublisherCategory,
    PublisherStatus,
    SubmissionMethod,
)
from app.core.exceptions import ValidationError as DomainValidationError
from app.schemas.common import CountryCode, LanguageCode, ReadSchemaBase, SchemaBase, Score


def _normalize_optional_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return normalize_url(value)
    except DomainValidationError as exc:
        raise ValueError(exc.message) from exc


class PublisherCreate(SchemaBase):
    """Add a publisher candidate.

    ``domain`` and ``normalized_domain`` are derived from ``website_url``
    server-side, so the stored canonical identity always matches the URL.
    """

    website_url: str = Field(max_length=2048, description="Absolute URL of the directory site")
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category: PublisherCategory | None = None
    country: CountryCode | None = Field(
        default=None, description="Leave empty for a global directory"
    )
    language: LanguageCode | None = None
    submission_url: str | None = Field(default=None, max_length=2048)
    contact_url: str | None = Field(default=None, max_length=2048)
    submission_method: SubmissionMethod = Field(default=SubmissionMethod.UNKNOWN)
    pricing_type: PricingType = Field(
        default=PricingType.UNKNOWN,
        description=(
            "Only FREE publishers may enter the submission workflow. PAID, MIXED and "
            "UNKNOWN may be recorded for research but can never be submitted."
        ),
    )
    link_type: LinkType = Field(default=LinkType.UNKNOWN)
    dofollow_supported: bool | None = None
    nofollow_supported: bool | None = None
    status: PublisherStatus = Field(default=PublisherStatus.DISCOVERED)

    @field_validator("website_url")
    @classmethod
    def _normalize_site(cls, value: str) -> str:
        try:
            return normalize_url(value)
        except DomainValidationError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("submission_url", "contact_url")
    @classmethod
    def _normalize_links(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)


class PublisherUpdate(SchemaBase):
    """Partial update.

    ``website_url`` is not updatable: the canonical domain is the row's
    identity and backs the per-tenant unique constraint.
    """

    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category: PublisherCategory | None = None
    country: CountryCode | None = None
    language: LanguageCode | None = None
    submission_url: str | None = Field(default=None, max_length=2048)
    contact_url: str | None = Field(default=None, max_length=2048)
    submission_method: SubmissionMethod | None = None
    pricing_type: PricingType | None = None
    link_type: LinkType | None = None
    dofollow_supported: bool | None = None
    nofollow_supported: bool | None = None
    status: PublisherStatus | None = None

    @field_validator("submission_url", "contact_url")
    @classmethod
    def _normalize_links(cls, value: str | None) -> str | None:
        return _normalize_optional_url(value)


class PublisherRead(ReadSchemaBase):
    id: UUID
    domain: str
    normalized_domain: str = Field(description="Canonical form used for de-duplication")
    website_url: str
    name: str | None = None
    description: str | None = None
    category: str | None = None
    country: str | None = None
    language: str | None = None
    submission_url: str | None = None
    contact_url: str | None = None
    submission_method: str
    pricing_type: str
    link_type: str
    dofollow_supported: bool | None = None
    nofollow_supported: bool | None = None
    status: str
    quality_score: float | None = None
    relevance_score: float | None = None
    spam_score: float | None = None
    authority_score: float | None = None
    organic_traffic: int | None = None
    signals: dict[str, Any] = Field(
        default_factory=dict, description="Qualification evidence gathered by the crawler"
    )
    is_submittable: bool = Field(
        description="True only for FREE publishers in QUALIFIED status (MVP business rule)"
    )
    discovery_run_id: UUID | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DiscoveryRequest(SchemaBase):
    """Ask a discovery provider for free listing candidates."""

    provider: Annotated[str, StringConstraints(min_length=2, max_length=64)] = Field(
        default="seed_list",
        description="Discovery provider key. Use GET /publishers/discovery-providers to list.",
    )
    keywords: list[Annotated[str, StringConstraints(min_length=2, max_length=120)]] = Field(
        default_factory=list, max_length=20, description="Topic or industry terms"
    )
    country: CountryCode | None = None
    language: LanguageCode | None = None
    category: PublisherCategory | None = None
    campaign_id: UUID | None = Field(
        default=None, description="Associate the run with a campaign for reporting"
    )
    limit: int = Field(default=25, ge=1, le=200, description="Maximum candidates to return")
    #: Discovery only ever produces free-listing candidates in this MVP; the
    #: flag exists so the field is explicit in the API rather than implied.
    free_only: bool = Field(default=True, description="Always true; paid discovery is out of scope")
    run_async: bool = Field(
        default=True,
        description=(
            "Enqueue the run as a background job and return immediately. Set false to "
            "run inline, which is only appropriate for small limits."
        ),
    )

    @field_validator("free_only")
    @classmethod
    def _must_be_free(cls, value: bool) -> bool:
        if not value:
            raise ValueError("paid publisher discovery is out of scope for this platform")
        return value


class DiscoveryRunRead(ReadSchemaBase):
    id: UUID
    campaign_id: UUID | None = None
    provider: str
    query: dict[str, Any] = Field(default_factory=dict)
    status: str
    results_found: int
    publishers_created: int
    duplicates_skipped: int
    error: str | None = Field(default=None, description="Failure class only, never provider output")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DiscoveryProviderRead(ReadSchemaBase):
    """A discovery provider available to this tenant."""

    key: str
    name: str
    description: str
    requires_credential: bool = Field(
        description="Whether the tenant must configure a BYOK credential to use it"
    )
    available: bool = Field(description="False when a required credential is missing")


class QualificationRequest(SchemaBase):
    """Re-score a publisher."""

    fetch_live: bool = Field(
        default=True,
        description=(
            "Fetch the site to gather fresh signals. Set false to re-score from the "
            "signals already stored."
        ),
    )
    relevance_keywords: list[str] = Field(
        default_factory=list, max_length=20, description="Terms used to judge topical relevance"
    )
    target_country: CountryCode | None = None


class ScoreBreakdown(ReadSchemaBase):
    """Explains a score rather than just reporting it.

    Qualification is a judgement a user has to trust, so the individual
    components and the reasons are returned alongside the numbers.
    """

    quality_score: Score
    relevance_score: Score
    spam_score: Score
    authority_score: Score
    opportunity_score: Score = Field(description="Combined, weighted score used for ranking")
    components: dict[str, float] = Field(
        default_factory=dict, description="Per-signal contributions"
    )
    reasons: list[str] = Field(default_factory=list, description="Human-readable findings")
    recommended_status: str = Field(description="QUALIFIED or REJECTED under current thresholds")
    eligible_for_submission: bool = Field(
        description="Whether the MVP FREE-only rule permits submitting to this publisher"
    )


class QualificationResult(ReadSchemaBase):
    publisher: PublisherRead
    scores: ScoreBreakdown

"""Client website schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from app.core.domains import normalize_domain, normalize_url
from app.core.enums import ClientWebsiteStatus
from app.core.exceptions import ValidationError as DomainValidationError
from app.schemas.common import CountryCode, LanguageCode, ReadSchemaBase, SchemaBase

Name = Annotated[str, StringConstraints(min_length=2, max_length=200)]


def _validate_url(value: str) -> str:
    """Canonicalise a URL, translating the domain error into a Pydantic one."""
    try:
        return normalize_url(value)
    except DomainValidationError as exc:
        raise ValueError(exc.message) from exc


class ClientWebsiteCreate(SchemaBase):
    """Register a client site.

    Only ``website_url`` is required: ``domain`` and ``normalized_domain`` are
    derived from it server-side, so a client cannot submit a URL and a
    contradictory domain.
    """

    name: Name
    website_url: str = Field(max_length=2048, description="Absolute site URL")
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    target_country: CountryCode | None = None
    target_countries: list[CountryCode] = Field(
        default_factory=list, max_length=50, description="Additional target markets"
    )
    target_language: LanguageCode | None = None
    status: ClientWebsiteStatus = Field(default=ClientWebsiteStatus.ACTIVE)

    @field_validator("website_url")
    @classmethod
    def _normalize(cls, value: str) -> str:
        url = _validate_url(value)
        normalize_domain(url)  # rejects IPs, single-label and malformed hosts
        return url


class ClientWebsiteUpdate(SchemaBase):
    """Partial update.

    ``website_url`` is intentionally not updatable: it is the site's identity
    and backs the unique constraint. Pointing a campaign's client at a
    different domain should be a new client website, not an edit.
    """

    name: Name | None = None
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    target_country: CountryCode | None = None
    target_countries: list[CountryCode] | None = Field(default=None, max_length=50)
    target_language: LanguageCode | None = None
    status: ClientWebsiteStatus | None = None


class ClientWebsiteRead(ReadSchemaBase):
    id: UUID
    name: str
    domain: str
    normalized_domain: str = Field(description="Canonical form used for de-duplication")
    website_url: str
    description: str | None = None
    industry: str | None = None
    target_country: str | None = None
    target_countries: list[str] = Field(default_factory=list)
    target_language: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

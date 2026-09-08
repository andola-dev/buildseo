"""Campaign schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.core.enums import CampaignStatus
from app.schemas.common import CountryCode, LanguageCode, ReadSchemaBase, SchemaBase

Name = Annotated[str, StringConstraints(min_length=2, max_length=200)]


class CampaignCreate(SchemaBase):
    """Create a free-listing campaign for a client website.

    ``free_only`` is not accepted as an input at all. This platform builds free
    listings; the column is pinned true by a database CHECK, so exposing it
    would only let a client submit a value that is guaranteed to be rejected.
    """

    client_website_id: UUID
    name: Name
    description: str | None = Field(default=None, max_length=5000)
    status: CampaignStatus = Field(default=CampaignStatus.DRAFT)
    target_country: CountryCode | None = None
    target_language: LanguageCode | None = None
    budget: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description=(
            "Planning and reporting figure only. Nothing in this platform spends it: "
            "there are no paid placements to buy."
        ),
    )
    target_link_count: int | None = Field(default=None, gt=0, le=100_000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class CampaignUpdate(SchemaBase):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=5000)
    status: CampaignStatus | None = None
    target_country: CountryCode | None = None
    target_language: LanguageCode | None = None
    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    target_link_count: int | None = Field(default=None, gt=0, le=100_000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class CampaignRead(ReadSchemaBase):
    id: UUID
    client_website_id: UUID
    name: str
    description: str | None = None
    status: str
    target_country: str | None = None
    target_language: str | None = None
    budget: Decimal | None = None
    free_only: bool = Field(description="Always true in this MVP; enforced by the database")
    target_link_count: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime
    updated_at: datetime


class CampaignStats(ReadSchemaBase):
    """Progress counters for a campaign."""

    campaign_id: UUID
    opportunities_total: int
    opportunities_qualified: int
    opportunities_ready: int
    submissions_total: int
    submissions_published: int
    submissions_verified: int
    target_link_count: int | None = None

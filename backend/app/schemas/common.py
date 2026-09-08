"""Shared schema base classes and field types."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _stringify_ip(value: object) -> object:
    """asyncpg maps a Postgres INET column to ``IPv4Address``/``IPv6Address``."""
    if isinstance(value, (IPv4Address, IPv6Address)):
        return str(value)
    return value


#: ISO 3166-1 alpha-2, upper-cased.
CountryCode = Annotated[
    str,
    StringConstraints(min_length=2, max_length=2, to_upper=True, pattern=r"^[A-Za-z]{2}$"),
]
#: ISO 639-1, optionally with a region suffix (``en``, ``pt-BR``).
LanguageCode = Annotated[
    str,
    StringConstraints(min_length=2, max_length=8, pattern=r"^[A-Za-z]{2}(-[A-Za-z0-9]{2,5})?$"),
]
Slug = Annotated[
    str,
    StringConstraints(
        min_length=3, max_length=64, to_lower=True, pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$"
    ),
]
RoleSlug = Annotated[
    str,
    StringConstraints(
        min_length=3, max_length=64, to_lower=True, pattern=r"^[a-z0-9][a-z0-9_]{1,62}[a-z0-9]$"
    ),
]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
#: 0-100 normalised score.
Score = Annotated[float, Field(ge=0, le=100)]
#: Accepts the ``IPv4Address``/``IPv6Address`` a Postgres INET column round-trips as.
IPAddressStr = Annotated[str, BeforeValidator(_stringify_ip)]


class SchemaBase(BaseModel):
    """Request schemas: reject unknown fields.

    ``extra="forbid"`` turns a typo'd or stale field name into a 422 instead of
    silently ignoring it, which matters when the ignored field is something
    like ``pricing_type``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReadSchemaBase(BaseModel):
    """Response schemas: built from ORM objects, field-by-field."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class TimestampedRead(ReadSchemaBase):
    """Mixin for entities exposing both timestamps."""

    created_at: object = Field(description="Creation time (UTC)")
    updated_at: object = Field(description="Last modification time (UTC)")


class IdRef(SchemaBase):
    """A bare reference to another resource."""

    id: UUID = Field(description="Resource identifier")

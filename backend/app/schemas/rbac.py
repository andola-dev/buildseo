"""Role and permission schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from app.schemas.common import ReadSchemaBase, RoleSlug, SchemaBase


class PermissionRead(ReadSchemaBase):
    """A catalog entry."""

    id: UUID
    code: str = Field(description="Permission code, ``resource.action``")
    resource: str
    action: str
    description: str | None = None


class RoleRead(ReadSchemaBase):
    id: UUID
    slug: str
    name: str
    description: str | None = None
    is_system: bool = Field(
        description="System roles are seeded per workspace and cannot be edited or deleted"
    )
    permissions: list[str] = Field(default_factory=list, description="Granted permission codes")
    created_at: datetime
    updated_at: datetime


class RoleCreate(SchemaBase):
    """Create a custom role.

    Custom roles need no schema change: they are ordinary rows with
    ``is_system = false`` and an explicit permission list.
    """

    slug: RoleSlug
    name: Annotated[str, StringConstraints(min_length=2, max_length=120)]
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] = Field(
        min_length=1,
        description="Permission codes to grant. Every code must exist in the catalog.",
    )


class RoleUpdate(SchemaBase):
    name: Annotated[str, StringConstraints(min_length=2, max_length=120)] | None = None
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] | None = Field(
        default=None, min_length=1, description="Replaces the role's permission set entirely"
    )

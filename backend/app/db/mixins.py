"""Reusable column mixins.

``TenantOwnedMixin`` is the one that matters: applying it is what marks a table
as tenant-owned, and the RLS migration and its schema-audit test both key off
the presence of a ``tenant_id`` column. A model that stores tenant data and
forgets this mixin fails the audit test rather than silently going unprotected.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.ids import uuid7


class UUIDPrimaryKeyMixin:
    """UUIDv7 primary key generated in the application.

    Generating ids client-side lets a service build associated rows (and the
    AAD that binds a credential ciphertext to its row) before the INSERT,
    without a round trip.
    """

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid7, sort_order=-100
    )


class TimestampMixin:
    """``created_at`` / ``updated_at``, both maintained by the database.

    Defaults are server-side (``now()``) and ``updated_at`` is additionally
    maintained by the ``set_updated_at`` trigger, so a raw SQL UPDATE or a
    background job that bypasses the ORM still gets a correct timestamp.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
    )


class CreatedAtMixin:
    """``created_at`` only, for append-only tables (audit logs, AI usage)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, sort_order=100
    )


class TenantOwnedMixin:
    """Marks a table as tenant-owned and adds the RLS discriminator column.

    ``declared_attr`` is required because a mixin cannot own a ``ForeignKey``
    shared across several mapped classes.
    """

    @declared_attr.directive
    @classmethod
    def tenant_id(cls) -> Mapped[UUID]:
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE", name=f"fk_{cls.__tablename__}_tenant_id"),
            nullable=False,
            index=True,
            sort_order=-99,
        )

"""Background jobs (the database-backed task queue)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import JobStatus


class Job(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    """A unit of deferred work.

    PostgreSQL is the queue for the MVP: ``SELECT … FOR UPDATE SKIP LOCKED``
    gives safe multi-worker claiming with no extra infrastructure, and the job
    rows are transactional with the domain changes that enqueue them — so a
    rolled-back request never leaves an orphaned job. The ``TaskQueue`` protocol
    keeps this swappable for Celery/Dramatiq/ARQ/Temporal later.

    ``tenant_id`` is carried so a worker can re-establish the same tenant
    context (and therefore the same RLS protection) that the enqueuing request
    had.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        # Idempotent enqueue: a caller may supply a key so a retried request
        # does not schedule the same work twice.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency_key"),
        CheckConstraint(JobStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        # The claim query's covering index: pending work whose time has come,
        # oldest first. Partial, so it does not grow with completed history.
        Index(
            "ix_jobs_claimable",
            "run_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_jobs_tenant_id_status", "tenant_id", "status"),
        Index("ix_jobs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_jobs_task_name_status", "task_name", "status"),
        {"comment": "Tenant-owned background jobs. Claimed with FOR UPDATE SKIP LOCKED."},
    )

    #: Registry key of the handler, e.g. ``publisher.qualify``.
    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Handler arguments. Must never contain a secret; handlers resolve
    #: credentials themselves from the credential service.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{JobStatus.PENDING.value}'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    #: Earliest execution time; also the retry-backoff mechanism.
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Failure class and message, truncated. Never a provider response body.
    last_error: Mapped[str | None] = mapped_column(Text)
    #: The user whose action enqueued the job, for audit correlation.
    enqueued_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

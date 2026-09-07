"""AI usage accounting."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, TenantOwnedMixin, UUIDPrimaryKeyMixin
from app.models.enums import AiOperation, AiUsageStatus


class AiUsageRecord(Base, UUIDPrimaryKeyMixin, TenantOwnedMixin, CreatedAtMixin):
    """One AI request, successful or not.

    Append-only, so there is no ``updated_at``. Deliberately records *no*
    prompt and no completion text: the accepted output is already stored in
    ``generated_contents`` where it can be reviewed, and duplicating prompts
    here would multiply the amount of tenant business data at rest for no
    accounting benefit. Provider keys are, of course, never recorded.

    Token counts and cost are nullable because not every provider returns
    usage; ``estimated_cost`` is explicitly an estimate priced by the
    application, not a provider invoice.
    """

    __tablename__ = "ai_usage_records"
    __table_args__ = (
        CheckConstraint(AiOperation.check_constraint("operation"), name="operation_valid"),
        CheckConstraint(AiUsageStatus.check_constraint("status"), name="status_valid"),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="input_tokens_valid"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_valid"),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0", name="estimated_cost_valid"
        ),
        Index("ix_ai_usage_records_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_ai_usage_records_tenant_id_provider_model", "tenant_id", "provider", "model"),
        Index("ix_ai_usage_records_tenant_id_operation", "tenant_id", "operation"),
        {"comment": "Tenant-owned AI usage ledger. Append-only; stores no prompts."},
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Free-form purpose tag, e.g. ``content_generation``.
    purpose: Mapped[str | None] = mapped_column(String(48))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    #: Correlates the AI call with the request or job that made it.
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{AiUsageStatus.SUCCEEDED.value}'")
    )
    #: Failure class for a failed call. Never a provider response body.
    error_code: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

"""AI usage accounting schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ReadSchemaBase


class AiUsageRead(ReadSchemaBase):
    """One recorded AI call.

    No prompt or completion text is stored, so none can be returned: the
    accepted output already lives in ``generated_contents`` where a human
    reviewed it.
    """

    id: UUID
    provider: str
    model: str
    operation: str
    purpose: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: Decimal | None = Field(
        default=None, description="Application-side estimate, not a provider invoice"
    )
    request_id: str | None = Field(
        default=None, description="Correlates with the HTTP request or job that made the call"
    )
    status: str
    error_code: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class AiUsageSummaryRow(ReadSchemaBase):
    """Aggregated usage for one provider/model/operation."""

    provider: str
    model: str
    operation: str
    requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    failures: int


class AiUsageSummary(ReadSchemaBase):
    rows: list[AiUsageSummaryRow]
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost: float
    since: datetime | None = None
    until: datetime | None = None

"""AI usage accounting.

Every AI call is recorded, successful or not, so a tenant can see what its
providers are costing before the invoice arrives.

Two deliberate omissions: no prompt and no completion text. The accepted
output already lives in ``generated_contents`` where a human reviewed it, and
duplicating prompts here would multiply the amount of tenant business data at
rest for no accounting benefit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config.logging import get_logger
from app.core.context import get_request_id
from app.core.enums import AiOperation, AiUsageStatus
from app.core.pagination import Page, PageParams, SortParams
from app.db.session import TenantAwareSession
from app.integrations.ai.base import EmbeddingResult, GenerationResult
from app.models.ai_usage import AiUsageRecord
from app.repositories.ai_usage import AiUsageRepository
from app.schemas.ai import AiUsageSummary, AiUsageSummaryRow

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-million-token prices used for the cost estimate."""

    input_per_million: float
    output_per_million: float


#: Indicative prices for the cost *estimate* only. Deliberately a small,
#: overridable table rather than an authoritative price list: vendor pricing
#: changes without notice, so ``estimated_cost`` is documented as an estimate
#: and an unknown model simply records no cost rather than a wrong one.
MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(2.50, 10.00),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
    "text-embedding-3-small": ModelPrice(0.02, 0.0),
    "text-embedding-3-large": ModelPrice(0.13, 0.0),
    "claude-opus-5": ModelPrice(5.00, 25.00),
    "claude-sonnet-5": ModelPrice(2.00, 10.00),
    "claude-haiku-4-5": ModelPrice(1.00, 5.00),
    "gemini-2.5-pro": ModelPrice(1.25, 10.00),
    "gemini-2.5-flash": ModelPrice(0.30, 2.50),
}


def estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Estimate the cost of a call, or ``None`` when the model is unpriced."""
    price = MODEL_PRICES.get(model)
    if price is None or (input_tokens is None and output_tokens is None):
        return None
    total = ((input_tokens or 0) / 1_000_000) * price.input_per_million
    total += ((output_tokens or 0) / 1_000_000) * price.output_per_million
    return round(total, 6)


class AiUsageService:
    """Writes and reports the AI usage ledger."""

    def __init__(self, *, session: TenantAwareSession, repository: AiUsageRepository) -> None:
        self._session = session
        self._repository = repository

    async def record_generation(
        self, result: GenerationResult, *, purpose: str | None = None
    ) -> AiUsageRecord:
        return await self._record(
            provider=result.provider,
            model=result.model,
            operation=AiOperation.GENERATE,
            purpose=purpose,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            status=AiUsageStatus.SUCCEEDED,
        )

    async def record_embedding(
        self, result: EmbeddingResult, *, purpose: str | None = None
    ) -> AiUsageRecord:
        return await self._record(
            provider=result.provider,
            model=result.model,
            operation=AiOperation.EMBED,
            purpose=purpose,
            input_tokens=result.input_tokens,
            output_tokens=None,
            latency_ms=result.latency_ms,
            status=AiUsageStatus.SUCCEEDED,
        )

    async def record_failure(
        self,
        *,
        provider: str,
        model: str,
        operation: AiOperation,
        error_code: str,
        purpose: str | None = None,
    ) -> AiUsageRecord:
        """Record a failed call.

        Failures are counted too: a provider whose key has expired shows up as
        a spike of failures rather than as silence.
        """
        return await self._record(
            provider=provider,
            model=model,
            operation=operation,
            purpose=purpose,
            input_tokens=None,
            output_tokens=None,
            latency_ms=None,
            status=AiUsageStatus.FAILED,
            error_code=error_code,
        )

    async def _record(
        self,
        *,
        provider: str,
        model: str,
        operation: AiOperation,
        purpose: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        status: AiUsageStatus,
        error_code: str | None = None,
    ) -> AiUsageRecord:
        record = self._repository.new(
            provider=provider,
            model=model,
            operation=operation.value,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimate_cost(model, input_tokens, output_tokens),
            # Ties the AI call back to the HTTP request or job that made it.
            request_id=get_request_id(),
            status=status.value,
            error_code=error_code,
            latency_ms=latency_ms,
        )
        await self._repository.flush()
        return record

    async def list(
        self,
        *,
        page: PageParams,
        sort: SortParams | None,
        provider: str | None = None,
        model: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Page[AiUsageRecord]:
        filters = self._repository.build_filters(
            provider=provider,
            model=model,
            operation=operation,
            status=status,
            since=since,
            until=until,
        )
        return await self._repository.list_page(page=page, sort=sort, filters=filters)

    async def summary(
        self, *, since: datetime | None = None, until: datetime | None = None
    ) -> AiUsageSummary:
        rows = await self._repository.summarize(since=since, until=until)
        parsed = [AiUsageSummaryRow(**row) for row in rows]  # type: ignore[arg-type]
        return AiUsageSummary(
            rows=parsed,
            total_requests=sum(row.requests for row in parsed),
            total_input_tokens=sum(row.input_tokens for row in parsed),
            total_output_tokens=sum(row.output_tokens for row in parsed),
            total_estimated_cost=round(sum(row.estimated_cost for row in parsed), 6),
            since=since,
            until=until,
        )

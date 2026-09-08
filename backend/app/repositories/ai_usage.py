"""AI usage ledger data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.ai_usage import AiUsageRecord
from app.repositories.base import TenantRepository


class AiUsageRepository(TenantRepository[AiUsageRecord]):
    """Append-only. The runtime role has no UPDATE or DELETE on this table."""

    model = AiUsageRecord
    sortable_fields = frozenset({"created_at", "provider", "model", "operation"})
    default_sort = "created_at"

    async def summarize(
        self, *, since: datetime | None = None, until: datetime | None = None
    ) -> list[dict[str, object]]:
        """Per provider/model rollup for the tenant's usage dashboard.

        Aggregated in the database rather than by loading rows: a busy tenant
        can accumulate hundreds of thousands of records and they must never be
        pulled into memory to be counted.
        """
        statement = (
            select(
                AiUsageRecord.provider,
                AiUsageRecord.model,
                AiUsageRecord.operation,
                func.count().label("requests"),
                func.coalesce(func.sum(AiUsageRecord.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(AiUsageRecord.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(AiUsageRecord.estimated_cost), 0).label("estimated_cost"),
                func.count().filter(AiUsageRecord.status == "FAILED").label("failures"),
            )
            .where(AiUsageRecord.tenant_id == self.tenant_id)
            .group_by(AiUsageRecord.provider, AiUsageRecord.model, AiUsageRecord.operation)
            .order_by(AiUsageRecord.provider, AiUsageRecord.model)
        )
        if since:
            statement = statement.where(AiUsageRecord.created_at >= since)
        if until:
            statement = statement.where(AiUsageRecord.created_at < until)

        rows = (await self.session.execute(statement)).all()
        return [
            {
                "provider": row.provider,
                "model": row.model,
                "operation": row.operation,
                "requests": int(row.requests),
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "estimated_cost": float(row.estimated_cost),
                "failures": int(row.failures),
            }
            for row in rows
        ]

    def build_filters(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if provider:
            filters.append(AiUsageRecord.provider == provider)
        if model:
            filters.append(AiUsageRecord.model == model)
        if operation:
            filters.append(AiUsageRecord.operation == operation)
        if status:
            filters.append(AiUsageRecord.status == status)
        if since:
            filters.append(AiUsageRecord.created_at >= since)
        if until:
            filters.append(AiUsageRecord.created_at < until)
        return filters

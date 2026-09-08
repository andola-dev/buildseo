"""Audit trail endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, PaginatedResponse, paginated
from app.rbac.catalog import Perm
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get(
    "",
    summary="Read the audit trail",
    description=(
        "Security- and business-significant actions in this workspace, newest "
        "first.\n\n"
        "The trail is append-only: there is no update or delete endpoint, and the "
        "application's own database role has `UPDATE` and `DELETE` revoked on the "
        "table, so it cannot rewrite its history even through a bug.\n\n"
        "`metadata` is assembled from per-action allow-lists rather than from raw "
        "request bodies, so it cannot contain a password or an API key.\n\n"
        "Sortable fields: `created_at`, `action`, `resource_type`."
    ),
    response_model=PaginatedResponse[AuditLogRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.AUDIT_READ))],
)
async def list_audit_logs(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    action: Annotated[str | None, Query(description="Exact action code")] = None,
    user_id: Annotated[UUID | None, Query(description="Filter by actor")] = None,
    resource_type: Annotated[str | None, Query()] = None,
    resource_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query(description="Inclusive lower bound")] = None,
    until: Annotated[datetime | None, Query(description="Exclusive upper bound")] = None,
) -> PaginatedResponse[AuditLogRead]:
    filters = services.audit_logs.build_filters(
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        since=since,
        until=until,
    )
    result = await services.audit_logs.list_page(page=page, sort=sort, filters=filters)
    return paginated(
        [AuditLogRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )

"""Per-workspace AI configuration and usage accounting."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.audit.actions import AuditAction
from app.core.exceptions import ResourceNotFoundError
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.ai import AiUsageRead, AiUsageSummary
from app.schemas.credentials import AiConfigRead, AiConfigUpsert

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get(
    "/configs",
    summary="List AI configuration",
    description=(
        "Which provider, model and credential this workspace uses for each "
        "purpose (`content_generation`, `discovery`, `qualification`, "
        "`embedding`).\n\n"
        "Business code asks for a purpose, never a vendor, so switching provider "
        "is a change here rather than a deployment."
    ),
    response_model=ApiResponse[list[AiConfigRead]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.INTEGRATION_READ))],
)
async def list_ai_configs(services: ServicesDep) -> ApiResponse[list[AiConfigRead]]:
    rows = await services.ai_configs.list_all()
    return ok([AiConfigRead.model_validate(row) for row in rows], total=len(rows))


@router.put(
    "/configs",
    summary="Set AI configuration for a purpose",
    description=(
        "Creates or replaces the configuration for one purpose.\n\n"
        "Setting `is_default` moves the default to this provider; exactly one "
        "default per purpose is enforced by a partial unique index. Every "
        "provider except a self-hosted `custom` endpoint requires a credential, "
        "which must already exist in this workspace."
    ),
    response_model=ApiResponse[AiConfigRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.INTEGRATION_UPDATE))],
)
async def upsert_ai_config(
    payload: AiConfigUpsert, services: ServicesDep
) -> ApiResponse[AiConfigRead]:
    if payload.credential_id is not None:
        # Confirms the credential exists in this workspace before pointing a
        # configuration at it; the FK is RESTRICT, so a bad id would otherwise
        # surface as a constraint error.
        await services.credential_service.get(payload.credential_id)

    if payload.is_default:
        # The partial unique index does not allow two defaults for a purpose to
        # coexist, even momentarily inside the transaction.
        await services.ai_configs.clear_default_for_purpose(payload.purpose.value)

    existing = await services.ai_configs.get_for_purpose_and_provider(
        purpose=payload.purpose.value, provider=payload.provider.value
    )
    if existing is None:
        config = services.ai_configs.new(
            purpose=payload.purpose.value,
            provider=payload.provider.value,
            model=payload.model,
            credential_id=payload.credential_id,
            parameters=payload.parameters,
            is_default=payload.is_default,
        )
    else:
        existing.model = payload.model
        existing.credential_id = payload.credential_id
        existing.parameters = payload.parameters
        existing.is_default = payload.is_default
        config = existing
    await services.ai_configs.flush()

    await services.audit.record(
        AuditAction.AI_CONFIG_UPDATED,
        resource_type="tenant_ai_config",
        resource_id=config.id,
        metadata={
            "purpose": config.purpose,
            "provider": config.provider,
            "model": config.model,
            "is_default": config.is_default,
        },
    )
    return ok(AiConfigRead.model_validate(config))


@router.delete(
    "/configs/{config_id}",
    summary="Remove an AI configuration",
    description="Removes one provider configuration. Other purposes are unaffected.",
    response_model=ApiResponse[dict],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.INTEGRATION_DELETE))],
)
async def delete_ai_config(config_id: UUID, services: ServicesDep) -> ApiResponse[dict]:
    config = await services.ai_configs.get(config_id)
    if config is None:
        raise ResourceNotFoundError.for_resource("tenant_ai_config", config_id)
    purpose, provider = config.purpose, config.provider
    await services.ai_configs.delete(config)
    await services.ai_configs.flush()
    await services.audit.record(
        AuditAction.AI_CONFIG_UPDATED,
        resource_type="tenant_ai_config",
        resource_id=config_id,
        metadata={"purpose": purpose, "provider": provider, "reason": "deleted"},
    )
    return ok({"deleted": True})


@router.get(
    "/usage",
    summary="List AI usage",
    description=(
        "The workspace's AI call ledger, successful and failed.\n\n"
        "No prompt or completion text is stored, so none is returned: the accepted "
        "output lives in the opportunity's generated content, where a person "
        "reviewed it. `estimated_cost` is an application-side estimate, not a "
        "provider invoice."
    ),
    response_model=PaginatedResponse[AiUsageRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.AI_USAGE_READ))],
)
async def list_ai_usage(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    provider: Annotated[str | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    operation: Annotated[str | None, Query(description="generate or embed")] = None,
    usage_status: Annotated[str | None, Query(alias="status")] = None,
    since: Annotated[datetime | None, Query(description="Inclusive lower bound")] = None,
    until: Annotated[datetime | None, Query(description="Exclusive upper bound")] = None,
) -> PaginatedResponse[AiUsageRead]:
    result = await services.ai_usage_service.list(
        page=page,
        sort=sort,
        provider=provider,
        model=model,
        operation=operation,
        status=usage_status,
        since=since,
        until=until,
    )
    return paginated(
        [AiUsageRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get(
    "/usage/summary",
    summary="AI usage summary",
    description=(
        "Per provider/model/operation rollup with token counts, estimated cost and "
        "failure counts. Aggregated in the database, so it stays cheap for a "
        "workspace with hundreds of thousands of records."
    ),
    response_model=ApiResponse[AiUsageSummary],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.AI_USAGE_READ))],
)
async def ai_usage_summary(
    services: ServicesDep,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[AiUsageSummary]:
    return ok(await services.ai_usage_service.summary(since=since, until=until))

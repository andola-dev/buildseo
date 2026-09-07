"""Campaign endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.campaigns import CampaignCreate, CampaignRead, CampaignStats, CampaignUpdate

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

CampaignIdPath = Annotated[UUID, Path(description="Campaign identifier")]


@router.get(
    "",
    summary="List campaigns",
    description=(
        "Free-listing campaigns in this workspace.\n\n"
        "Sortable fields: `created_at`, `updated_at`, `name`, `status`, "
        "`start_date`, `end_date`."
    ),
    response_model=PaginatedResponse[CampaignRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_READ))],
)
async def list_campaigns(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    campaign_status: Annotated[str | None, Query(alias="status")] = None,
    client_website_id: Annotated[UUID | None, Query()] = None,
    target_country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> PaginatedResponse[CampaignRead]:
    result = await services.campaign_service.list(
        page=page,
        sort=sort,
        status=campaign_status,
        client_website_id=client_website_id,
        target_country=target_country,
        search=q,
    )
    return paginated(
        [CampaignRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign",
    description=(
        "Creates a campaign for a client website. Country and language are "
        "inherited from the client site when not given.\n\n"
        "`free_only` is not an input: this platform builds free listings, and the "
        "column is pinned true by a database constraint. `budget` is recorded for "
        "planning only — nothing here spends it, because there are no paid "
        "placements to buy."
    ),
    response_model=ApiResponse[CampaignRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_CREATE))],
)
async def create_campaign(
    payload: CampaignCreate, services: ServicesDep
) -> ApiResponse[CampaignRead]:
    campaign = await services.campaign_service.create(payload)
    return ok(CampaignRead.model_validate(campaign))


@router.get(
    "/{campaign_id}",
    summary="Get a campaign",
    response_model=ApiResponse[CampaignRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_READ))],
)
async def get_campaign(
    campaign_id: CampaignIdPath, services: ServicesDep
) -> ApiResponse[CampaignRead]:
    campaign = await services.campaign_service.get(campaign_id)
    return ok(CampaignRead.model_validate(campaign))


@router.patch(
    "/{campaign_id}",
    summary="Update a campaign",
    response_model=ApiResponse[CampaignRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_UPDATE))],
)
async def update_campaign(
    campaign_id: CampaignIdPath, payload: CampaignUpdate, services: ServicesDep
) -> ApiResponse[CampaignRead]:
    campaign = await services.campaign_service.update(campaign_id, payload)
    return ok(CampaignRead.model_validate(campaign))


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a campaign",
    description="Deletes the campaign and cascades to its opportunities and submissions.",
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_DELETE))],
)
async def delete_campaign(campaign_id: CampaignIdPath, services: ServicesDep) -> None:
    await services.campaign_service.delete(campaign_id)


@router.get(
    "/{campaign_id}/stats",
    summary="Campaign progress",
    description=(
        "Opportunity and submission counters for a campaign. Counted in the "
        "database, so this stays cheap for a campaign with six figures of "
        "opportunities."
    ),
    response_model=ApiResponse[CampaignStats],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CAMPAIGN_READ))],
)
async def campaign_stats(
    campaign_id: CampaignIdPath, services: ServicesDep
) -> ApiResponse[CampaignStats]:
    return ok(await services.campaign_service.stats(campaign_id))

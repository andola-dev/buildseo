"""Client website endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.client_websites import (
    ClientWebsiteCreate,
    ClientWebsiteRead,
    ClientWebsiteUpdate,
)

router = APIRouter(prefix="/client-websites", tags=["Client Websites"])

WebsiteIdPath = Annotated[UUID, Path(description="Client website identifier")]


@router.get(
    "",
    summary="List client websites",
    description=(
        "The client sites this workspace builds links for.\n\n"
        "Sortable fields: `created_at`, `updated_at`, `name`, `normalized_domain`, "
        "`status`. `q` searches name and domain."
    ),
    response_model=PaginatedResponse[ClientWebsiteRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CLIENT_WEBSITE_READ))],
)
async def list_client_websites(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    website_status: Annotated[str | None, Query(alias="status")] = None,
    industry: Annotated[str | None, Query(description="Filter by industry")] = None,
    target_country: Annotated[
        str | None, Query(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    ] = None,
) -> PaginatedResponse[ClientWebsiteRead]:
    result = await services.client_website_service.list(
        page=page,
        sort=sort,
        status=website_status,
        industry=industry,
        target_country=target_country,
        search=q,
    )
    return paginated(
        [ClientWebsiteRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a client website",
    description=(
        "Registers a client site. Only `website_url` is required for identity: the "
        "canonical domain is derived from it server-side, so `https://www.Example.com/` "
        "and `example.com` cannot become two rows.\n\n"
        "A duplicate canonical domain returns 409 with the existing id."
    ),
    response_model=ApiResponse[ClientWebsiteRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CLIENT_WEBSITE_CREATE))],
)
async def create_client_website(
    payload: ClientWebsiteCreate, services: ServicesDep
) -> ApiResponse[ClientWebsiteRead]:
    website = await services.client_website_service.create(payload)
    return ok(ClientWebsiteRead.model_validate(website))


@router.get(
    "/{website_id}",
    summary="Get a client website",
    response_model=ApiResponse[ClientWebsiteRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CLIENT_WEBSITE_READ))],
)
async def get_client_website(
    website_id: WebsiteIdPath, services: ServicesDep
) -> ApiResponse[ClientWebsiteRead]:
    website = await services.client_website_service.get(website_id)
    return ok(ClientWebsiteRead.model_validate(website))


@router.patch(
    "/{website_id}",
    summary="Update a client website",
    description=(
        "Partial update. `website_url` is not editable: it is the site's identity "
        "and backs the uniqueness constraint. Pointing a client at a different "
        "domain is a new client website."
    ),
    response_model=ApiResponse[ClientWebsiteRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CLIENT_WEBSITE_UPDATE))],
)
async def update_client_website(
    website_id: WebsiteIdPath, payload: ClientWebsiteUpdate, services: ServicesDep
) -> ApiResponse[ClientWebsiteRead]:
    website = await services.client_website_service.update(website_id, payload)
    return ok(ClientWebsiteRead.model_validate(website))


@router.delete(
    "/{website_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a client website",
    description=(
        "Deletes the site and cascades to its campaigns, and therefore to their "
        "opportunities and submissions."
    ),
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CLIENT_WEBSITE_DELETE))],
)
async def delete_client_website(website_id: WebsiteIdPath, services: ServicesDep) -> None:
    await services.client_website_service.delete(website_id)

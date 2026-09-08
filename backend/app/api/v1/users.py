"""Workspace user directory."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.api.dependencies.tenant import TenantContextDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.users import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    summary="List workspace users",
    description=(
        "Users who are members of the active workspace.\n\n"
        "`users` is a global table, so this listing is confined by a membership "
        "join rather than by a row policy: a caller can only ever see their own "
        "workspace's members.\n\n"
        "Sortable fields: `created_at`, `updated_at`, `email`, `last_login_at`."
    ),
    response_model=PaginatedResponse[UserRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_READ))],
)
async def list_users(
    context: TenantContextDep,
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    membership_status: Annotated[
        str | None, Query(alias="status", description="Filter by membership status")
    ] = None,
) -> PaginatedResponse[UserRead]:
    result = await services.user_service.list_tenant_members(
        tenant_id=context.tenant_id,
        page=page,
        sort=sort,
        search=q,
        membership_status=membership_status,
    )
    return paginated(
        [UserRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get(
    "/{user_id}",
    summary="Get a workspace user",
    description=(
        "A member of the active workspace. A user who exists but is not a member "
        "returns 404, not 403, so the endpoint cannot be used to probe the "
        "platform's user base."
    ),
    response_model=ApiResponse[UserRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_READ))],
)
async def get_user(
    user_id: Annotated[UUID, Path(description="User identifier")],
    context: TenantContextDep,
    services: ServicesDep,
) -> ApiResponse[UserRead]:
    user = await services.user_service.get_tenant_member(
        tenant_id=context.tenant_id, user_id=user_id
    )
    return ok(UserRead.model_validate(user))

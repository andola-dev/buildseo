"""Workspace and membership administration."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep, UnscopedServicesDep
from app.api.dependencies.tenant import TenantContext, TenantContextDep
from app.core.exceptions import TenantAccessError
from app.core.responses import (
    AUTH_ERROR_RESPONSES,
    CRUD_ERROR_RESPONSES,
    ApiResponse,
    PaginatedResponse,
    ok,
    paginated,
)
from app.rbac.catalog import Perm
from app.schemas.tenants import (
    MembershipCreate,
    MembershipRead,
    MembershipUpdate,
    TenantCreate,
    TenantRead,
    TenantUpdate,
)
from app.schemas.users import UserRead

router = APIRouter(tags=["Tenants"])

TenantIdPath = Annotated[UUID, Path(description="Workspace identifier")]


def _assert_path_matches_context(tenant_id: UUID, context: TenantContext) -> None:
    """Refuse a path id that is not the request's active workspace.

    The tenant context comes from the validated membership, not the path, so a
    mismatch means the caller is addressing a workspace this request is not
    scoped to. Refusing is clearer than silently acting on the active one.
    """
    if tenant_id != context.tenant_id:
        raise TenantAccessError(
            "This request is scoped to a different workspace. Switch with "
            "/auth/select-tenant or send a matching X-Tenant-ID header.",
            code="TENANT_CONTEXT_MISMATCH",
        )


@router.get(
    "/tenants",
    summary="List your workspaces",
    description="Workspaces the caller belongs to. Does not require an active workspace.",
    response_model=PaginatedResponse[TenantRead],
    responses=AUTH_ERROR_RESPONSES,
)
async def list_tenants(
    principal: PrincipalDep,
    services: UnscopedServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
) -> PaginatedResponse[TenantRead]:
    result = await services.tenants.list_for_user(principal.user_id, page=page, sort=sort)
    return paginated(
        [TenantRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "/tenants",
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
    description=(
        "Creates a workspace, seeds its five default roles, and makes the caller "
        "its owner.\n\n"
        "Any authenticated user may create a workspace; no permission applies "
        "because there is no existing workspace to hold a permission in."
    ),
    response_model=ApiResponse[TenantRead],
    responses=AUTH_ERROR_RESPONSES,
)
async def create_tenant(
    payload: TenantCreate, principal: PrincipalDep, services: UnscopedServicesDep
) -> ApiResponse[TenantRead]:
    tenant, _ = await services.tenant_service.create_tenant(
        name=payload.name, slug=payload.slug, owner=principal.user
    )
    return ok(TenantRead.model_validate(tenant))


@router.get(
    "/tenants/{tenant_id}",
    summary="Get a workspace",
    description="Details of the active workspace.",
    response_model=ApiResponse[TenantRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.TENANT_READ))],
)
async def get_tenant(tenant_id: TenantIdPath, context: TenantContextDep) -> ApiResponse[TenantRead]:
    _assert_path_matches_context(tenant_id, context)
    return ok(TenantRead.model_validate(context.tenant))


@router.patch(
    "/tenants/{tenant_id}",
    summary="Update a workspace",
    description=(
        "Changes the workspace's name, status or settings.\n\n"
        "`settings` holds non-sensitive preferences only — for example "
        '`{"scoring": {"relevance_weight": 0.5}}` to tune qualification. Keys '
        "that look like secrets are rejected: provider credentials belong in "
        "`/credentials`, where they are encrypted."
    ),
    response_model=ApiResponse[TenantRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.TENANT_UPDATE))],
)
async def update_tenant(
    tenant_id: TenantIdPath,
    payload: TenantUpdate,
    context: TenantContextDep,
    services: ServicesDep,
) -> ApiResponse[TenantRead]:
    _assert_path_matches_context(tenant_id, context)
    tenant = await services.tenant_service.update_tenant(
        tenant=context.tenant,
        name=payload.name,
        status=payload.status,
        settings=payload.settings,
    )
    return ok(TenantRead.model_validate(tenant))


@router.get(
    "/tenants/{tenant_id}/members",
    summary="List members",
    description="Members of the active workspace, with the roles each holds.",
    response_model=PaginatedResponse[MembershipRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_READ))],
)
async def list_members(
    tenant_id: TenantIdPath,
    context: TenantContextDep,
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    membership_status: Annotated[
        str | None, Query(alias="status", description="Filter by membership status")
    ] = None,
) -> PaginatedResponse[MembershipRead]:
    _assert_path_matches_context(tenant_id, context)
    result = await services.tenant_service.list_members(
        tenant_id=context.tenant_id, page=page, sort=sort, status=membership_status
    )

    rows: list[MembershipRead] = []
    users = {
        user.id: user
        for user in await services.users.get_many(
            [membership.user_id for membership in result.items]
        )
    }
    for membership in result.items:
        user = users.get(membership.user_id)
        rows.append(
            MembershipRead(
                id=membership.id,
                tenant_id=membership.tenant_id,
                user_id=membership.user_id,
                status=membership.status,
                is_owner=membership.is_owner,
                roles=await services.tenant_service.roles_for_membership(membership.id),
                user=UserRead.model_validate(user) if user else None,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
        )
    return paginated(rows, page=result.page, page_size=result.page_size, total=result.total)


@router.post(
    "/tenants/{tenant_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Add a member",
    description=(
        "Adds an existing account to the workspace with the given roles.\n\n"
        "This phase has no email delivery, so there are no invitations: the person "
        "must already have registered. An unmatched identifier returns 404 without "
        "revealing whether the account exists."
    ),
    response_model=ApiResponse[MembershipRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_CREATE))],
)
async def add_member(
    tenant_id: TenantIdPath,
    payload: MembershipCreate,
    context: TenantContextDep,
    services: ServicesDep,
) -> ApiResponse[MembershipRead]:
    _assert_path_matches_context(tenant_id, context)
    membership = await services.tenant_service.add_member(
        tenant_id=context.tenant_id,
        email=str(payload.email) if payload.email else None,
        user_id=payload.user_id,
        role_slugs=list(payload.role_slugs),
        status=payload.status,
    )
    return ok(
        MembershipRead(
            id=membership.id,
            tenant_id=membership.tenant_id,
            user_id=membership.user_id,
            status=membership.status,
            is_owner=membership.is_owner,
            roles=await services.tenant_service.roles_for_membership(membership.id),
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )
    )


@router.patch(
    "/tenants/{tenant_id}/members/{membership_id}",
    summary="Update a member",
    description=(
        "Changes a member's status, roles or ownership.\n\n"
        "The workspace's last active owner cannot be demoted, suspended or "
        "removed, so a workspace can never be left without one."
    ),
    response_model=ApiResponse[MembershipRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_UPDATE))],
)
async def update_member(
    tenant_id: TenantIdPath,
    membership_id: Annotated[UUID, Path(description="Membership identifier")],
    payload: MembershipUpdate,
    context: TenantContextDep,
    services: ServicesDep,
) -> ApiResponse[MembershipRead]:
    _assert_path_matches_context(tenant_id, context)
    membership = await services.tenant_service.update_member(
        tenant_id=context.tenant_id,
        membership_id=membership_id,
        status=payload.status,
        role_slugs=list(payload.role_slugs) if payload.role_slugs else None,
        is_owner=payload.is_owner,
    )
    return ok(
        MembershipRead(
            id=membership.id,
            tenant_id=membership.tenant_id,
            user_id=membership.user_id,
            status=membership.status,
            is_owner=membership.is_owner,
            roles=await services.tenant_service.roles_for_membership(membership.id),
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )
    )


@router.delete(
    "/tenants/{tenant_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member",
    description="Removes a member. The last active owner cannot be removed.",
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.USER_DELETE))],
)
async def remove_member(
    tenant_id: TenantIdPath,
    membership_id: Annotated[UUID, Path(description="Membership identifier")],
    context: TenantContextDep,
    services: ServicesDep,
) -> None:
    _assert_path_matches_context(tenant_id, context)
    await services.tenant_service.remove_member(
        tenant_id=context.tenant_id, membership_id=membership_id
    )

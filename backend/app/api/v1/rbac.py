"""Roles and the permission catalog."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.models.rbac import Role
from app.rbac.catalog import Perm
from app.schemas.rbac import PermissionRead, RoleCreate, RoleRead, RoleUpdate

router = APIRouter(tags=["RBAC"])


async def _to_read(role: Role, services: ServicesDep) -> RoleRead:
    return RoleRead(
        id=role.id,
        slug=role.slug,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=await services.rbac_service.permission_codes(role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get(
    "/permissions",
    summary="List permissions",
    description=(
        "The platform's permission catalog. Global and seeded: a permission code "
        "means the same thing in every workspace, so tenants compose them into "
        "roles rather than inventing codes."
    ),
    response_model=ApiResponse[list[PermissionRead]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PERMISSION_READ))],
)
async def list_permissions(services: ServicesDep) -> ApiResponse[list[PermissionRead]]:
    rows = await services.rbac_service.list_permissions()
    return ok([PermissionRead.model_validate(row) for row in rows], total=len(rows))


@router.get(
    "/roles",
    summary="List roles",
    description=(
        "Roles in the active workspace. Each workspace has its own copy of the "
        "five defaults (`owner`, `admin`, `seo_manager`, `seo_specialist`, "
        "`viewer`) plus any custom roles.\n\nSortable fields: `name`, `slug`, "
        "`created_at`, `updated_at`."
    ),
    response_model=PaginatedResponse[RoleRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.ROLE_READ))],
)
async def list_roles(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    is_system: Annotated[bool | None, Query(description="Filter to system or custom roles")] = None,
) -> PaginatedResponse[RoleRead]:
    result = await services.rbac_service.list_roles(page=page, sort=sort, is_system=is_system)
    rows = [await _to_read(role, services) for role in result.items]
    return paginated(rows, page=result.page, page_size=result.page_size, total=result.total)


@router.post(
    "/roles",
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role",
    description=(
        "Creates a role granting an explicit set of permission codes. Custom roles "
        "need no schema change — they are ordinary rows with `is_system = false`.\n\n"
        "Unknown permission codes are rejected rather than ignored: a role that "
        "looks like it grants something but does not is worse than an error."
    ),
    response_model=ApiResponse[RoleRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.ROLE_CREATE))],
)
async def create_role(payload: RoleCreate, services: ServicesDep) -> ApiResponse[RoleRead]:
    role = await services.rbac_service.create_role(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        permissions=list(payload.permissions),
    )
    return ok(await _to_read(role, services))


@router.get(
    "/roles/{role_id}",
    summary="Get a role",
    description="Fetches one role by id, including its permission codes.",
    response_model=ApiResponse[RoleRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.ROLE_READ))],
)
async def get_role(
    role_id: Annotated[UUID, Path(description="Role identifier")], services: ServicesDep
) -> ApiResponse[RoleRead]:
    role = await services.rbac_service.get_role(role_id)
    return ok(await _to_read(role, services))


@router.patch(
    "/roles/{role_id}",
    summary="Update a custom role",
    description=(
        "Renames a role or replaces its permission set.\n\n"
        "System roles are immutable: a workspace that could strip permissions from "
        "its own Owner role could lock itself out. Copy it into a custom role "
        "instead."
    ),
    response_model=ApiResponse[RoleRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.ROLE_UPDATE))],
)
async def update_role(
    role_id: Annotated[UUID, Path(description="Role identifier")],
    payload: RoleUpdate,
    services: ServicesDep,
) -> ApiResponse[RoleRead]:
    role = await services.rbac_service.update_role(
        role_id=role_id,
        name=payload.name,
        description=payload.description,
        permissions=list(payload.permissions) if payload.permissions else None,
    )
    return ok(await _to_read(role, services))


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom role",
    description=(
        "Deletes a custom role. Refused for a system role, and refused while the "
        "role is still assigned to a member — deleting it would silently strip "
        "their permissions."
    ),
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.ROLE_DELETE))],
)
async def delete_role(
    role_id: Annotated[UUID, Path(description="Role identifier")], services: ServicesDep
) -> None:
    await services.rbac_service.delete_role(role_id)

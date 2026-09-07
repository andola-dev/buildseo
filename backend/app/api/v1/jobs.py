"""Background job inspection."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.jobs import JobRead
from app.workers.registry import registered_tasks

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "",
    summary="List background jobs",
    description=(
        "Jobs enqueued by this workspace, with their status, attempt count and "
        "last error.\n\nSortable fields: `created_at`, `updated_at`, `status`, "
        "`task_name`, `run_at`."
    ),
    response_model=PaginatedResponse[JobRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.JOB_READ))],
)
async def list_jobs(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    job_status: Annotated[str | None, Query(alias="status")] = None,
    task_name: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[JobRead]:
    filters = services.jobs.build_filters(status=job_status, task_name=task_name)
    result = await services.jobs.list_page(page=page, sort=sort, filters=filters)
    return paginated(
        [JobRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get(
    "/task-types",
    summary="List task types",
    description="Task names a worker in this deployment can handle.",
    response_model=ApiResponse[list[str]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.JOB_READ))],
)
async def list_task_types() -> ApiResponse[list[str]]:
    return ok(list(registered_tasks()))


@router.get(
    "/{job_id}",
    summary="Get a job",
    description="The poll target returned by every endpoint that defers work.",
    response_model=ApiResponse[JobRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.JOB_READ))],
)
async def get_job(
    job_id: Annotated[UUID, Path(description="Job identifier")], services: ServicesDep
) -> ApiResponse[JobRead]:
    job = await services.jobs.get_or_raise(job_id, resource="job")
    return ok(JobRead.model_validate(job))

"""Publisher, discovery and qualification endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.integrations.discovery.base import DiscoveryQuery
from app.rbac.catalog import Perm
from app.schemas.jobs import JobAccepted
from app.schemas.publishers import (
    DiscoveryProviderRead,
    DiscoveryRequest,
    DiscoveryRunRead,
    PublisherCreate,
    PublisherRead,
    PublisherUpdate,
    QualificationRequest,
    QualificationResult,
)
from app.workers.registry import TASK_PUBLISHER_DISCOVERY, TASK_PUBLISHER_QUALIFY

router = APIRouter(prefix="/publishers", tags=["Publishers"])

PublisherIdPath = Annotated[UUID, Path(description="Publisher identifier")]


@router.get(
    "",
    summary="List publishers",
    description=(
        "Publisher candidates in this workspace.\n\n"
        "Use `free_only=true` with `status=QUALIFIED` to see exactly what is "
        "eligible for submission — that combination is served by a dedicated "
        "partial index.\n\nSortable fields: `created_at`, `updated_at`, `domain`, "
        "`normalized_domain`, `name`, `status`, `quality_score`, `relevance_score`, "
        "`spam_score`, `authority_score`, `organic_traffic`, `last_checked_at`. "
        "`q` searches name and domain."
    ),
    response_model=PaginatedResponse[PublisherRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_READ))],
)
async def list_publishers(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    publisher_status: Annotated[str | None, Query(alias="status")] = None,
    pricing_type: Annotated[str | None, Query(description="FREE, PAID, MIXED or UNKNOWN")] = None,
    category: Annotated[str | None, Query()] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    language: Annotated[str | None, Query(max_length=8)] = None,
    submission_method: Annotated[str | None, Query()] = None,
    min_quality_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_spam_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    free_only: Annotated[
        bool, Query(description="Restrict to FREE publishers (the submittable ones)")
    ] = False,
) -> PaginatedResponse[PublisherRead]:
    result = await services.publisher_service.list(
        page=page,
        sort=sort,
        status=publisher_status,
        pricing_type=pricing_type,
        category=category,
        country=country,
        language=language,
        submission_method=submission_method,
        min_quality_score=min_quality_score,
        max_spam_score=max_spam_score,
        free_only=free_only,
        search=q,
    )
    return paginated(
        [PublisherRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a publisher",
    description=(
        "Adds a candidate directory. The canonical domain is derived from "
        "`website_url` server-side, so the same site cannot be added twice under "
        "different URL forms; a duplicate returns 409 with the existing id.\n\n"
        "A publisher may be recorded with any `pricing_type`, but only `FREE` can "
        "ever enter a submission workflow."
    ),
    response_model=ApiResponse[PublisherRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_CREATE))],
)
async def create_publisher(
    payload: PublisherCreate, services: ServicesDep
) -> ApiResponse[PublisherRead]:
    publisher = await services.publisher_service.create(payload)
    return ok(PublisherRead.model_validate(publisher))


@router.get(
    "/discovery-providers",
    summary="List discovery providers",
    description=(
        "Discovery sources and whether this workspace can use each one. A provider "
        "needing a credential the workspace has not configured is reported as "
        "unavailable rather than failing when called."
    ),
    response_model=ApiResponse[list[DiscoveryProviderRead]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_READ))],
)
async def list_discovery_providers(
    services: ServicesDep,
) -> ApiResponse[list[DiscoveryProviderRead]]:
    rows = await services.discovery_registry.availability()
    return ok([DiscoveryProviderRead.model_validate(row) for row in rows])


@router.get(
    "/discovery-runs",
    summary="List discovery runs",
    description="Past and in-flight discovery runs, with their result counts.",
    response_model=PaginatedResponse[DiscoveryRunRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_READ))],
)
async def list_discovery_runs(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    run_status: Annotated[str | None, Query(alias="status")] = None,
    provider: Annotated[str | None, Query()] = None,
    campaign_id: Annotated[UUID | None, Query()] = None,
) -> PaginatedResponse[DiscoveryRunRead]:
    result = await services.discovery_service.list_runs(
        page=page, sort=sort, status=run_status, provider=provider, campaign_id=campaign_id
    )
    return paginated(
        [DiscoveryRunRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "/discover",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run publisher discovery",
    description=(
        "Searches a discovery provider for free-listing candidates, normalises "
        "them, and adds the ones this workspace does not already have.\n\n"
        "Discovery never asserts pricing: candidates land as `UNKNOWN` and "
        "`DISCOVERED`, so nothing becomes submittable until qualification has "
        "confirmed a free submission path.\n\n"
        "Defaults to running in the background and returning a job to poll. Set "
        "`run_async=false` to run inline, which is only sensible for small limits."
    ),
    response_model=ApiResponse[JobAccepted] | ApiResponse[DiscoveryRunRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_DISCOVER))],
)
async def discover_publishers(
    payload: DiscoveryRequest,
    services: ServicesDep,
    principal: PrincipalDep,
) -> ApiResponse[JobAccepted] | ApiResponse[DiscoveryRunRead]:
    query = DiscoveryQuery(
        keywords=tuple(payload.keywords),
        country=payload.country,
        language=payload.language,
        category=payload.category,
        limit=payload.limit,
        free_only=payload.free_only,
    )
    run = await services.discovery_service.start_run(
        provider_key=payload.provider, query=query, campaign_id=payload.campaign_id
    )

    if payload.run_async:
        enqueued = await services.task_queue.enqueue(
            TASK_PUBLISHER_DISCOVERY,
            {"run_id": str(run.id), "provider": payload.provider, **query.as_dict()},
            enqueued_by_user_id=principal.user_id,
        )
        return ok(
            JobAccepted(
                job_id=enqueued.job_id,
                task_name=enqueued.task_name,
                status=enqueued.status,
                poll_url=enqueued.poll_url,
            )
        )

    provider = await services.discovery_registry.resolve(payload.provider)
    run = await services.discovery_service.execute(run, provider=provider, query=query)
    return ok(DiscoveryRunRead.model_validate(run))


@router.get(
    "/{publisher_id}",
    summary="Get a publisher",
    response_model=ApiResponse[PublisherRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_READ))],
)
async def get_publisher(
    publisher_id: PublisherIdPath, services: ServicesDep
) -> ApiResponse[PublisherRead]:
    publisher = await services.publisher_service.get(publisher_id)
    return ok(PublisherRead.model_validate(publisher))


@router.patch(
    "/{publisher_id}",
    summary="Update a publisher",
    description=(
        "Partial update. `website_url` is not editable: the canonical domain is "
        "the row's identity and backs the uniqueness constraint."
    ),
    response_model=ApiResponse[PublisherRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_UPDATE))],
)
async def update_publisher(
    publisher_id: PublisherIdPath, payload: PublisherUpdate, services: ServicesDep
) -> ApiResponse[PublisherRead]:
    publisher = await services.publisher_service.update(publisher_id, payload)
    return ok(PublisherRead.model_validate(publisher))


@router.delete(
    "/{publisher_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a publisher",
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_DELETE))],
)
async def delete_publisher(publisher_id: PublisherIdPath, services: ServicesDep) -> None:
    await services.publisher_service.delete(publisher_id)


@router.post(
    "/{publisher_id}/qualify",
    summary="Qualify a publisher",
    description=(
        "Fetches the site, gathers signals, scores it, and sets its status.\n\n"
        "The crawler honours `robots.txt` and stops at any CAPTCHA or anti-bot "
        "challenge rather than working around it — such a site is reported as "
        "needing manual review.\n\n"
        "Pricing is only ever tightened automatically: a confirmed free submission "
        "path marks the publisher `FREE`, an explicit paid signal marks it `PAID`, "
        "and anything unconfirmed stays `UNKNOWN` and therefore un-submittable.\n\n"
        "Returns the score breakdown with the reasons behind it, not just the "
        "numbers. Scoring weights come from the workspace's own settings."
    ),
    response_model=ApiResponse[QualificationResult],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_QUALIFY))],
)
async def qualify_publisher(
    publisher_id: PublisherIdPath,
    payload: QualificationRequest,
    services: ServicesDep,
) -> ApiResponse[QualificationResult]:
    publisher, scores = await services.qualification_service.qualify_by_id(
        publisher_id,
        fetch_live=payload.fetch_live,
        relevance_keywords=tuple(payload.relevance_keywords),
        target_country=payload.target_country,
    )
    return ok(QualificationResult(publisher=PublisherRead.model_validate(publisher), scores=scores))


@router.post(
    "/{publisher_id}/qualify-async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Qualify a publisher in the background",
    description=(
        "Schedules qualification instead of waiting for the crawl. Preferred when "
        "qualifying many publishers, since each one involves live HTTP requests."
    ),
    response_model=ApiResponse[JobAccepted],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.PUBLISHER_QUALIFY))],
)
async def qualify_publisher_async(
    publisher_id: PublisherIdPath,
    payload: QualificationRequest,
    services: ServicesDep,
    principal: PrincipalDep,
) -> ApiResponse[JobAccepted]:
    # Confirms the publisher exists (and belongs to this workspace) before
    # scheduling work against it.
    await services.publisher_service.get(publisher_id)
    enqueued = await services.task_queue.enqueue(
        TASK_PUBLISHER_QUALIFY,
        {
            "publisher_id": str(publisher_id),
            "fetch_live": payload.fetch_live,
            "relevance_keywords": list(payload.relevance_keywords),
            "target_country": payload.target_country,
        },
        enqueued_by_user_id=principal.user_id,
    )
    return ok(
        JobAccepted(
            job_id=enqueued.job_id,
            task_name=enqueued.task_name,
            status=enqueued.status,
            poll_url=enqueued.poll_url,
        )
    )

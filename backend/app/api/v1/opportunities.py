"""Opportunity and generated-content endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.idempotency import IdempotencyGuardDep
from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.enums import OpportunityStatus
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.opportunities import workflow
from app.rbac.catalog import Perm
from app.schemas.opportunities import (
    ContentGenerationRequest,
    ContentReviewRequest,
    GeneratedContentRead,
    OpportunityCreate,
    OpportunityRead,
    OpportunityRejectRequest,
    OpportunityTransitionRequest,
    OpportunityUpdate,
)

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])

OpportunityIdPath = Annotated[UUID, Path(description="Opportunity identifier")]


@router.get(
    "",
    summary="List opportunities",
    description=(
        "Listing opportunities in this workspace.\n\n"
        "Sortable fields: `created_at`, `updated_at`, `status`, `priority`, "
        "`qualification_score`, `discovered_at`, `qualified_at`."
    ),
    response_model=PaginatedResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_READ))],
)
async def list_opportunities(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    opportunity_status: Annotated[str | None, Query(alias="status")] = None,
    campaign_id: Annotated[UUID | None, Query()] = None,
    publisher_id: Annotated[UUID | None, Query()] = None,
    opportunity_type: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    min_priority: Annotated[int | None, Query(ge=0, le=100)] = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
) -> PaginatedResponse[OpportunityRead]:
    result = await services.opportunity_service.list(
        page=page,
        sort=sort,
        status=opportunity_status,
        campaign_id=campaign_id,
        publisher_id=publisher_id,
        opportunity_type=opportunity_type,
        category=category,
        min_priority=min_priority,
        min_score=min_score,
        search=q,
    )
    return paginated(
        [OpportunityRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create an opportunity",
    description=(
        "Pairs a campaign with a publisher.\n\n"
        "Only `FREE` publishers are accepted: a paid one is refused here so it "
        "never reaches a work queue at all.\n\n"
        "Idempotent by nature — repeating the call with the same campaign, "
        "publisher and target URL returns the existing opportunity with 200 "
        "instead of creating a duplicate. An `Idempotency-Key` header additionally "
        "replays the original response for any retried request."
    ),
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_CREATE))],
)
async def create_opportunity(
    payload: OpportunityCreate,
    services: ServicesDep,
    guard: IdempotencyGuardDep,
    response: Response,
) -> ApiResponse[OpportunityRead]:
    body = payload.model_dump(mode="json")
    replay = await guard.existing(body)
    if replay is not None and replay.resource_id:
        opportunity = await services.opportunity_service.get(UUID(replay.resource_id))
        response.status_code = status.HTTP_200_OK
        return ok(OpportunityRead.model_validate(opportunity), replayed=True)

    opportunity, created = await services.opportunity_service.create(payload)
    if not created:
        response.status_code = status.HTTP_200_OK
    read = OpportunityRead.model_validate(opportunity)
    await guard.remember(
        body,
        status_code=response.status_code or status.HTTP_201_CREATED,
        body=read.model_dump(mode="json"),
        resource_id=str(opportunity.id),
    )
    return ok(read, created=created)


@router.get(
    "/state-machine",
    summary="Opportunity state machine",
    description=(
        "The permitted status transitions, so a client can render exactly the "
        "actions the backend will accept."
    ),
    response_model=ApiResponse[dict],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_READ))],
)
async def opportunity_state_machine() -> ApiResponse[dict]:
    return ok(workflow.describe())


@router.get(
    "/{opportunity_id}",
    summary="Get an opportunity",
    description="Fetches one link opportunity by id.",
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_READ))],
)
async def get_opportunity(
    opportunity_id: OpportunityIdPath, services: ServicesDep
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.get(opportunity_id)
    return ok(OpportunityRead.model_validate(opportunity))


@router.patch(
    "/{opportunity_id}",
    summary="Update an opportunity",
    description=(
        "Edits the suggested copy, category or priority. Status is not editable "
        "here — lifecycle changes go through the transition endpoints so each move "
        "is validated and audited."
    ),
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def update_opportunity(
    opportunity_id: OpportunityIdPath, payload: OpportunityUpdate, services: ServicesDep
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.update(opportunity_id, payload)
    return ok(OpportunityRead.model_validate(opportunity))


@router.delete(
    "/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an opportunity",
    description="Deletes a link opportunity.",
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_DELETE))],
)
async def delete_opportunity(opportunity_id: OpportunityIdPath, services: ServicesDep) -> None:
    await services.opportunity_service.delete(opportunity_id)


@router.post(
    "/{opportunity_id}/qualify",
    summary="Qualify an opportunity",
    description=(
        "Scores the opportunity from its publisher's qualification and sets its "
        "priority.\n\n"
        "It inherits the publisher's judgement rather than re-crawling: quality is "
        "a property of the site, so scoring it once per publisher avoids hundreds "
        "of duplicate fetches across a campaign. An opportunity whose publisher is "
        "not a qualified free listing site is rejected with the reason recorded."
    ),
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def qualify_opportunity(
    opportunity_id: OpportunityIdPath, services: ServicesDep
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.qualify(opportunity_id)
    return ok(OpportunityRead.model_validate(opportunity))


@router.post(
    "/{opportunity_id}/select",
    summary="Select an opportunity",
    description="Marks a qualified opportunity as chosen for its campaign.",
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def select_opportunity(
    opportunity_id: OpportunityIdPath, services: ServicesDep
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.transition(
        opportunity_id, target=OpportunityStatus.SELECTED
    )
    return ok(OpportunityRead.model_validate(opportunity))


@router.post(
    "/{opportunity_id}/reject",
    summary="Reject an opportunity",
    description="Rejects an opportunity. A reason is required and is recorded on the row.",
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def reject_opportunity(
    opportunity_id: OpportunityIdPath,
    payload: OpportunityRejectRequest,
    services: ServicesDep,
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.transition(
        opportunity_id, target=OpportunityStatus.REJECTED, reason=payload.reason
    )
    return ok(OpportunityRead.model_validate(opportunity))


@router.post(
    "/{opportunity_id}/transition",
    summary="Transition an opportunity",
    description=(
        "Moves an opportunity to an explicit status, validated against the state "
        "machine. An illegal move returns 409 rather than writing a state nobody "
        "checked."
    ),
    response_model=ApiResponse[OpportunityRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def transition_opportunity(
    opportunity_id: OpportunityIdPath,
    payload: OpportunityTransitionRequest,
    services: ServicesDep,
) -> ApiResponse[OpportunityRead]:
    opportunity = await services.opportunity_service.transition(
        opportunity_id, target=payload.target_status, reason=payload.reason
    )
    return ok(OpportunityRead.model_validate(opportunity))


# --------------------------------------------------------------------------- #
# AI listing content
# --------------------------------------------------------------------------- #


@router.post(
    "/{opportunity_id}/generate-content",
    summary="Generate listing content",
    description=(
        "Drafts listing copy with the workspace's configured AI provider and "
        "stores it for review.\n\n"
        "Which vendor runs is not a parameter — it comes from the workspace's "
        "`content_generation` configuration, so switching provider is a settings "
        "change.\n\n"
        "The draft is always persisted before it can be submitted, with the "
        "provider, model and timestamp that produced it. Existing drafts are "
        "superseded rather than deleted, so the history behind an approval stays "
        "inspectable. Regenerating over an already-approved draft requires "
        "`regenerate=true`."
    ),
    response_model=ApiResponse[GeneratedContentRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.AI_GENERATE))],
)
async def generate_content(
    opportunity_id: OpportunityIdPath,
    payload: ContentGenerationRequest,
    services: ServicesDep,
) -> ApiResponse[GeneratedContentRead]:
    content = await services.content_service.generate(
        opportunity_id=opportunity_id, payload=payload
    )
    return ok(GeneratedContentRead.model_validate(content))


@router.get(
    "/{opportunity_id}/content",
    summary="List generated content",
    description="Every draft for an opportunity, newest first, including superseded ones.",
    response_model=ApiResponse[list[GeneratedContentRead]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_READ))],
)
async def list_content(
    opportunity_id: OpportunityIdPath, services: ServicesDep
) -> ApiResponse[list[GeneratedContentRead]]:
    rows = await services.content_service.list_for_opportunity(opportunity_id)
    return ok([GeneratedContentRead.model_validate(row) for row in rows], total=len(rows))


@router.post(
    "/{opportunity_id}/content/{content_id}/review",
    summary="Review generated content",
    description=(
        "Records a human decision on a draft, optionally with corrections.\n\n"
        "Only an `APPROVED` draft can be used by a submission, which is what makes "
        "the workflow human-in-the-loop rather than merely human-visible. "
        "Corrections are allow-listed to the content fields, and the original text "
        "remains in the superseded history."
    ),
    response_model=ApiResponse[GeneratedContentRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.OPPORTUNITY_UPDATE))],
)
async def review_content(
    opportunity_id: OpportunityIdPath,
    content_id: Annotated[UUID, Path(description="Generated content identifier")],
    payload: ContentReviewRequest,
    services: ServicesDep,
    principal: PrincipalDep,
) -> ApiResponse[GeneratedContentRead]:
    content = await services.content_service.review(
        content_id=content_id, payload=payload, reviewer_id=principal.user_id
    )
    return ok(GeneratedContentRead.model_validate(content))

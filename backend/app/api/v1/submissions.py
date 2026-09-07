"""Submission workflow endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.idempotency import IdempotencyGuardDep
from app.api.dependencies.pagination import PageParamsDep, SearchQuery, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.jobs import JobAccepted
from app.schemas.submissions import (
    SubmissionApproveRequest,
    SubmissionCreate,
    SubmissionExecuteRequest,
    SubmissionRead,
    SubmissionStateMachineRead,
    SubmissionTransitionRequest,
    SubmissionUpdate,
    SubmissionVerifyRequest,
)
from app.submissions import workflow
from app.workers.registry import TASK_SUBMISSION_VERIFY

router = APIRouter(prefix="/submissions", tags=["Submissions"])

SubmissionIdPath = Annotated[UUID, Path(description="Submission identifier")]


@router.get(
    "",
    summary="List submissions",
    description=(
        "Submissions in this workspace.\n\n"
        "Sortable fields: `created_at`, `updated_at`, `status`, `submitted_at`, "
        "`published_at`, `verified_at`, `approved_at`."
    ),
    response_model=PaginatedResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_READ))],
)
async def list_submissions(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    q: SearchQuery = None,
    submission_status: Annotated[str | None, Query(alias="status")] = None,
    campaign_id: Annotated[UUID | None, Query()] = None,
    opportunity_id: Annotated[UUID | None, Query()] = None,
    submission_method: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[SubmissionRead]:
    result = await services.submission_service.list(
        page=page,
        sort=sort,
        status=submission_status,
        campaign_id=campaign_id,
        opportunity_id=opportunity_id,
        submission_method=submission_method,
        search=q,
    )
    return paginated(
        [SubmissionRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Prepare a submission",
    description=(
        "Prepares a submission for an opportunity. **Sends nothing** — it starts "
        "in `READY` and must be reviewed and approved before it can be executed.\n\n"
        "Refused unless the publisher is `FREE` (checked here, again at execution, "
        "and independently by a database trigger) and the opportunity is `SELECTED` "
        "or `READY`.\n\n"
        "By default the title and description come from the opportunity's "
        "**approved** AI draft, so what a person signed off is what gets sent.\n\n"
        "One live submission per opportunity; a `FAILED` or `REJECTED` attempt can "
        "be retried with a fresh row."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_CREATE))],
)
async def create_submission(
    payload: SubmissionCreate,
    services: ServicesDep,
    guard: IdempotencyGuardDep,
    response: Response,
) -> ApiResponse[SubmissionRead]:
    body = payload.model_dump(mode="json")
    replay = await guard.existing(body)
    if replay is not None and replay.resource_id:
        submission = await services.submission_service.get(UUID(replay.resource_id))
        response.status_code = status.HTTP_200_OK
        return ok(SubmissionRead.model_validate(submission), replayed=True)

    submission = await services.submission_service.create(payload)
    read = SubmissionRead.model_validate(submission)
    await guard.remember(
        body,
        status_code=status.HTTP_201_CREATED,
        body=read.model_dump(mode="json"),
        resource_id=str(submission.id),
    )
    return ok(read)


@router.get(
    "/state-machine",
    summary="Submission state machine",
    description=(
        "The permitted transitions, the terminal statuses, and which statuses "
        "require a recorded approval.\n\n"
        "`PENDING_APPROVAL -> SUBMITTED` is the human-in-the-loop gate: no other "
        "path reaches `SUBMITTED`."
    ),
    response_model=ApiResponse[SubmissionStateMachineRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_READ))],
)
async def submission_state_machine() -> ApiResponse[SubmissionStateMachineRead]:
    return ok(SubmissionStateMachineRead(**workflow.describe()))  # type: ignore[arg-type]


@router.get(
    "/review-queue",
    summary="Submissions awaiting approval",
    description=(
        "The human review queue: submissions in `PENDING_APPROVAL`, oldest first. "
        "Served by a dedicated partial index."
    ),
    response_model=ApiResponse[list[SubmissionRead]],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_READ))],
)
async def review_queue(
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApiResponse[list[SubmissionRead]]:
    rows = await services.submission_service.review_queue(limit=limit)
    return ok([SubmissionRead.model_validate(row) for row in rows], total=len(rows))


@router.get(
    "/{submission_id}",
    summary="Get a submission",
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_READ))],
)
async def get_submission(
    submission_id: SubmissionIdPath, services: ServicesDep
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.get(submission_id)
    return ok(SubmissionRead.model_validate(submission))


@router.patch(
    "/{submission_id}",
    summary="Update a submission",
    description=(
        "Edits the payload of a submission that has not been sent.\n\n"
        "Editing an already-approved submission clears the approval and returns it "
        "to `IN_PROGRESS`: otherwise a reviewer's sign-off could be applied to "
        "content they never saw."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_UPDATE))],
)
async def update_submission(
    submission_id: SubmissionIdPath, payload: SubmissionUpdate, services: ServicesDep
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.update(submission_id, payload)
    return ok(SubmissionRead.model_validate(submission))


@router.delete(
    "/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a submission",
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_DELETE))],
)
async def delete_submission(submission_id: SubmissionIdPath, services: ServicesDep) -> None:
    await services.submission_service.delete(submission_id)


@router.post(
    "/{submission_id}/submit-for-review",
    summary="Send a submission for review",
    description=(
        "Moves a submission into `PENDING_APPROVAL`. Requires a title, so a "
        "reviewer always has something concrete to look at."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_UPDATE))],
)
async def submit_for_review(
    submission_id: SubmissionIdPath, services: ServicesDep
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.prepare_for_review(submission_id)
    return ok(SubmissionRead.model_validate(submission))


@router.post(
    "/{submission_id}/approve",
    summary="Approve a submission",
    description=(
        "Records the human approval that unlocks sending, naming the approver.\n\n"
        "Held behind its own `submission.approve` permission, which the SEO "
        "Specialist role deliberately lacks: preparing work and authorising it are "
        "separate duties. A database CHECK independently refuses any submission "
        "that reaches `SUBMITTED` without this record."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_APPROVE))],
)
async def approve_submission(
    submission_id: SubmissionIdPath,
    payload: SubmissionApproveRequest,
    services: ServicesDep,
    principal: PrincipalDep,
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.approve(
        submission_id, approver_id=principal.user_id, payload=payload
    )
    return ok(SubmissionRead.model_validate(submission))


@router.post(
    "/{submission_id}/execute",
    summary="Execute a submission",
    description=(
        "Performs or records the submission. Requires an existing approval, and "
        "re-checks the FREE-only rule in case the publisher's pricing was "
        "corrected since approval.\n\n"
        "`MANUAL` (the default) records that a person is doing the submission. "
        "`FORM` pre-flights the target and, whenever a CAPTCHA, anti-bot "
        "challenge, login or automation restriction is present, hands it back to a "
        "human with the reason recorded — publisher controls are respected, never "
        "circumvented."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_UPDATE))],
)
async def execute_submission(
    submission_id: SubmissionIdPath,
    payload: SubmissionExecuteRequest,
    services: ServicesDep,
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.execute(submission_id, payload=payload)
    return ok(SubmissionRead.model_validate(submission))


@router.post(
    "/{submission_id}/verify",
    summary="Verify a published link",
    description=(
        "Fetches the published page and checks that the client's link is really "
        "there, recording the anchor text and `rel` attribute as evidence.\n\n"
        "Matching is on canonical domain plus path, so a directory that adds "
        "tracking parameters or wraps the URL still verifies. A `nofollow` link is "
        "recorded as such, not failed — many free directories nofollow by policy.\n\n"
        "Set `fetch_live=false` with `manual_result` to record a human's finding."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_VERIFY))],
)
async def verify_submission(
    submission_id: SubmissionIdPath,
    payload: SubmissionVerifyRequest,
    services: ServicesDep,
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.verify(submission_id, payload=payload)
    return ok(SubmissionRead.model_validate(submission))


@router.post(
    "/{submission_id}/verify-async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Verify in the background",
    description="Schedules verification instead of waiting for the page fetch.",
    response_model=ApiResponse[JobAccepted],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_VERIFY))],
)
async def verify_submission_async(
    submission_id: SubmissionIdPath,
    payload: SubmissionVerifyRequest,
    services: ServicesDep,
    principal: PrincipalDep,
) -> ApiResponse[JobAccepted]:
    await services.submission_service.get(submission_id)
    enqueued = await services.task_queue.enqueue(
        TASK_SUBMISSION_VERIFY,
        {"submission_id": str(submission_id), "published_url": payload.published_url},
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


@router.post(
    "/{submission_id}/transition",
    summary="Transition a submission",
    description=(
        "Moves a submission to an explicit status, validated against the state "
        "machine. Not a way around the approval gate: an approval-gated target "
        "still requires the approval record."
    ),
    response_model=ApiResponse[SubmissionRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.SUBMISSION_UPDATE))],
)
async def transition_submission(
    submission_id: SubmissionIdPath,
    payload: SubmissionTransitionRequest,
    services: ServicesDep,
) -> ApiResponse[SubmissionRead]:
    submission = await services.submission_service.transition(
        submission_id, target=payload.target_status, reason=payload.reason
    )
    return ok(SubmissionRead.model_validate(submission))

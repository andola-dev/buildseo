"""BYOK credential endpoints.

Every response here is metadata. No endpoint in this router — or anywhere in
the API — returns a decrypted provider secret, and the response schema has no
field capable of carrying one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.dependencies.idempotency import IdempotencyGuardDep
from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.rbac import require_permission
from app.api.dependencies.services import ServicesDep
from app.core.responses import CRUD_ERROR_RESPONSES, ApiResponse, PaginatedResponse, ok, paginated
from app.rbac.catalog import Perm
from app.schemas.credentials import (
    CredentialCreate,
    CredentialRead,
    CredentialUpdate,
    CredentialVerifyResult,
)

router = APIRouter(prefix="/credentials", tags=["Credentials"])

CredentialIdPath = Annotated[UUID, Path(description="Credential identifier")]


@router.get(
    "",
    summary="List credentials",
    description=(
        "Configured provider credentials, as metadata only: provider, label, "
        "status, a masked hint such as `sk-****abcd`, and timestamps.\n\n"
        "There is no endpoint that reveals a stored secret. To change one, PATCH a "
        "new value."
    ),
    response_model=PaginatedResponse[CredentialRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_READ))],
)
async def list_credentials(
    services: ServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
    provider: Annotated[str | None, Query(description="Filter by provider key")] = None,
    provider_type: Annotated[str | None, Query()] = None,
    credential_status: Annotated[str | None, Query(alias="status")] = None,
) -> PaginatedResponse[CredentialRead]:
    result = await services.credential_service.list(
        page=page,
        sort=sort,
        provider=provider,
        provider_type=provider_type,
        status=credential_status,
    )
    return paginated(
        [CredentialRead.model_validate(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Store a credential",
    description=(
        "Stores a provider API key for this workspace.\n\n"
        "The secret is encrypted with a per-credential data key, itself wrapped by "
        "the deployment's master key, and bound to this workspace, this row and "
        "this provider — a ciphertext copied elsewhere fails to decrypt. Only a "
        "masked hint is ever readable afterwards.\n\n"
        "`metadata` is stored unencrypted and returned by the API, so keys that "
        "look like secrets are rejected there: the secret belongs in `secret`."
    ),
    response_model=ApiResponse[CredentialRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_CREATE))],
)
async def create_credential(
    payload: CredentialCreate,
    services: ServicesDep,
    guard: IdempotencyGuardDep,
    response: Response,
) -> ApiResponse[CredentialRead]:
    # The fingerprint deliberately excludes the secret: a retry of the same
    # logical request must match, and the digest is stored.
    body = payload.model_dump(mode="json", exclude={"secret"})
    replay = await guard.existing(body)
    if replay is not None and replay.resource_id:
        credential = await services.credential_service.get(UUID(replay.resource_id))
        response.status_code = status.HTTP_200_OK
        return ok(CredentialRead.model_validate(credential), replayed=True)

    credential = await services.credential_service.create(payload)
    if payload.verify:
        credential, _ = await services.credential_verification_service.verify(credential)

    read = CredentialRead.model_validate(credential)
    await guard.remember(
        body,
        status_code=status.HTTP_201_CREATED,
        body=read.model_dump(mode="json"),
        resource_id=str(credential.id),
    )
    return ok(read)


@router.get(
    "/{credential_id}",
    summary="Get a credential",
    description="Metadata for one credential. Never the secret.",
    response_model=ApiResponse[CredentialRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_READ))],
)
async def get_credential(
    credential_id: CredentialIdPath, services: ServicesDep
) -> ApiResponse[CredentialRead]:
    credential = await services.credential_service.get(credential_id)
    return ok(CredentialRead.model_validate(credential))


@router.patch(
    "/{credential_id}",
    summary="Update or rotate a credential",
    description=(
        "Renames, disables, or rotates a credential. Supplying `secret` replaces "
        "the stored key and resets its status to `CONFIGURED`, since a rotated key "
        "is unproven until used or verified."
    ),
    response_model=ApiResponse[CredentialRead],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_UPDATE))],
)
async def update_credential(
    credential_id: CredentialIdPath, payload: CredentialUpdate, services: ServicesDep
) -> ApiResponse[CredentialRead]:
    credential = await services.credential_service.update(credential_id, payload)
    if payload.verify:
        credential, _ = await services.credential_verification_service.verify(credential)
    return ok(CredentialRead.model_validate(credential))


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a credential",
    description=(
        "Deletes a credential. Refused while an AI configuration still points at "
        "it — silently disabling generation is worse than an explicit error."
    ),
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_DELETE))],
)
async def delete_credential(credential_id: CredentialIdPath, services: ServicesDep) -> None:
    await services.credential_service.delete(credential_id)


@router.post(
    "/{credential_id}/verify",
    summary="Verify a credential",
    description=(
        "Makes a minimal live call to confirm the key works, and records the "
        "outcome.\n\n"
        "A rejected key is marked `INVALID` so later requests stop retrying it. "
        "Only a failure *class* is returned — never the provider's response body, "
        "which frequently echoes the submitted key back."
    ),
    response_model=ApiResponse[CredentialVerifyResult],
    responses=CRUD_ERROR_RESPONSES,
    dependencies=[Depends(require_permission(Perm.CREDENTIAL_UPDATE))],
)
async def verify_credential(
    credential_id: CredentialIdPath, services: ServicesDep
) -> ApiResponse[CredentialVerifyResult]:
    credential = await services.credential_service.get(credential_id)
    credential, outcome = await services.credential_verification_service.verify(credential)
    return ok(
        CredentialVerifyResult(
            credential_id=credential.id,
            provider=credential.provider,
            status=credential.status,
            verified=outcome.verified,
            error_code=outcome.error_code,
            checked_at=outcome.checked_at or datetime.now(UTC),
        )
    )

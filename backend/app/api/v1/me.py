"""The authenticated user's own profile and workspaces."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.pagination import PageParamsDep, SortParamsDep
from app.api.dependencies.services import AuthServiceDep, UnscopedServicesDep
from app.core.responses import AUTH_ERROR_RESPONSES, ApiResponse, ok
from app.schemas.tenants import TenantRead
from app.schemas.users import (
    MeRead,
    PasswordChangeRequest,
    TenantMembershipSummary,
    UserRead,
    UserUpdate,
)

router = APIRouter(tags=["Users"])


@router.get(
    "/me",
    summary="Current user",
    description=(
        "The authenticated user, the workspaces they belong to, and their "
        "effective permissions in the active workspace.\n\n"
        "Permissions are resolved from the database on every call rather than read "
        "from the token, so a role change is reflected immediately."
    ),
    response_model=ApiResponse[MeRead],
    responses=AUTH_ERROR_RESPONSES,
)
async def read_me(
    principal: PrincipalDep,
    services: UnscopedServicesDep,
    auth: AuthServiceDep,
) -> ApiResponse[MeRead]:
    memberships = await services.memberships.list_for_user(principal.user_id)
    roles_by_membership = {
        membership.id: [
            role.slug
            for role in await services.membership_roles.list_roles_for_membership(
                membership.id, tenant_id=membership.tenant_id
            )
        ]
        # Role names are tenant-owned, so they can only be read for the
        # workspace this request is scoped to; other workspaces list as empty.
        for membership in memberships
        if principal.claimed_tenant_id == membership.tenant_id
    }
    summaries: list[TenantMembershipSummary] = await services.user_service.membership_summaries(
        principal.user_id, roles_by_membership=roles_by_membership
    )

    permissions: list[str] = []
    if principal.claimed_tenant_id is not None:
        permissions = sorted(
            await auth.effective_permissions(
                user_id=principal.user_id, tenant_id=principal.claimed_tenant_id
            )
        )

    return ok(
        MeRead(
            user=UserRead.model_validate(principal.user),
            active_tenant_id=principal.claimed_tenant_id,
            tenants=summaries,
            permissions=permissions,
        )
    )


@router.patch(
    "/me",
    summary="Update your profile",
    description=(
        "Changes the caller's own name. Email is the login identity and is not " "editable here."
    ),
    response_model=ApiResponse[UserRead],
    responses=AUTH_ERROR_RESPONSES,
)
async def update_me(
    payload: UserUpdate, principal: PrincipalDep, services: UnscopedServicesDep
) -> ApiResponse[UserRead]:
    user = await services.user_service.update_profile(
        user=principal.user, first_name=payload.first_name, last_name=payload.last_name
    )
    return ok(UserRead.model_validate(user))


@router.post(
    "/me/password",
    summary="Change your password",
    description=(
        "Requires the current password even though the caller is authenticated, so "
        "a stolen access token is not enough to take over the account.\n\n"
        "By default every other device is signed out; the calling session keeps "
        "working."
    ),
    response_model=ApiResponse[dict],
    responses=AUTH_ERROR_RESPONSES,
)
async def change_password(
    payload: PasswordChangeRequest, principal: PrincipalDep, auth: AuthServiceDep
) -> ApiResponse[dict]:
    revoked = await auth.change_password(
        user=principal.user,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
        revoke_other_sessions=payload.revoke_other_sessions,
        current_session_id=principal.session_id,
    )
    return ok({"revoked_sessions": revoked})


@router.get(
    "/me/tenants",
    summary="Your workspaces",
    description="The workspaces the caller may enter. Available without selecting one.",
    response_model=ApiResponse[list[TenantRead]],
    responses=AUTH_ERROR_RESPONSES,
)
async def list_my_tenants(
    principal: PrincipalDep,
    services: UnscopedServicesDep,
    page: PageParamsDep,
    sort: SortParamsDep,
) -> ApiResponse[list[TenantRead]]:
    result = await services.tenants.list_for_user(principal.user_id, page=page, sort=sort)
    return ok(
        [TenantRead.model_validate(tenant) for tenant in result.items],
        total=result.total,
    )

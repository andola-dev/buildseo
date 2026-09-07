"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, status

from app.api.dependencies.auth import PrincipalDep
from app.api.dependencies.services import AuthServiceDep, UnscopedServicesDep
from app.core.responses import AUTH_ERROR_RESPONSES, ERROR_RESPONSE_SCHEMA, ApiResponse, ok
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SelectTenantRequest,
    SessionRead,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

_PUBLIC_ERRORS = {code: ERROR_RESPONSE_SCHEMA[code] for code in (400, 401, 409, 422, 429, 500)}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Registers a user and, when `tenant_name` is supplied, creates a workspace "
        "the new user owns (with the five default roles seeded into it) and returns "
        "a token pair already scoped to it.\n\n"
        "No email is sent: this phase has no email functionality, so the account is "
        "usable immediately and `is_verified` stays false."
    ),
    response_model=ApiResponse[TokenPair],
    responses=_PUBLIC_ERRORS,
)
async def register(
    payload: RegisterRequest,
    auth: AuthServiceDep,
    services: UnscopedServicesDep,
) -> ApiResponse[TokenPair]:
    user = await auth.register_user(
        email=str(payload.email),
        password=payload.password.get_secret_value(),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )

    tenant_id: UUID | None = None
    if payload.tenant_name:
        tenant, _ = await services.tenant_service.create_tenant(
            name=payload.tenant_name, slug=payload.tenant_slug, owner=user
        )
        tenant_id = tenant.id

    pair = await auth.login(
        email=str(payload.email),
        password=payload.password.get_secret_value(),
        requested_tenant_id=tenant_id,
    )
    return ok(pair)


@router.post(
    "/login",
    summary="Log in",
    description=(
        "Exchanges credentials for an access token and a refresh token.\n\n"
        "An unknown email and a wrong password return the same error, and take the "
        "same amount of work, so this endpoint cannot be used to discover which "
        "addresses are registered.\n\n"
        "The active workspace is chosen from `tenant_id` when supplied (membership "
        "is validated), or automatically when the user belongs to exactly one. A "
        "user in several workspaces receives a token with no workspace and must "
        "call `/auth/select-tenant`."
    ),
    response_model=ApiResponse[TokenPair],
    responses=_PUBLIC_ERRORS,
)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> ApiResponse[TokenPair]:
    pair = await auth.login(
        email=str(payload.email),
        password=payload.password.get_secret_value(),
        requested_tenant_id=payload.tenant_id,
    )
    return ok(pair)


@router.post(
    "/refresh",
    summary="Rotate the refresh token",
    description=(
        "Exchanges a refresh token for a new pair. The presented token is revoked, "
        "so exactly one token per login is ever valid.\n\n"
        "Presenting an already-used token is treated as a leak: the entire token "
        "family descended from that login is revoked and the call fails.\n\n"
        "The remembered workspace is re-validated against membership, so a token "
        "cannot outlive the access it represents."
    ),
    response_model=ApiResponse[TokenPair],
    responses=_PUBLIC_ERRORS,
)
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> ApiResponse[TokenPair]:
    pair = await auth.refresh(refresh_token=payload.refresh_token.get_secret_value())
    return ok(pair)


@router.post(
    "/logout",
    summary="Log out",
    description=(
        "Revokes the session behind the supplied refresh token, or every session "
        "for the user when `all_sessions` is true. Revoking a session also "
        "invalidates its access tokens immediately.\n\n"
        "Idempotent: logging out with an unrecognised token succeeds without "
        "revealing whether it existed."
    ),
    response_model=ApiResponse[dict],
    responses=AUTH_ERROR_RESPONSES,
)
async def logout(
    payload: LogoutRequest, principal: PrincipalDep, auth: AuthServiceDep
) -> ApiResponse[dict]:
    revoked = await auth.logout(
        user_id=principal.user_id,
        session_id=principal.session_id,
        refresh_token=(payload.refresh_token.get_secret_value() if payload.refresh_token else None),
        all_sessions=payload.all_sessions,
    )
    return ok({"revoked_sessions": revoked})


@router.post(
    "/select-tenant",
    summary="Switch the active workspace",
    description=(
        "Issues a new access token scoped to `tenant_id`, after validating that the "
        "caller is an active member of it.\n\n"
        "The refresh token is not rotated: switching workspace is not a "
        "re-authentication. The choice is remembered on the session, so a later "
        "refresh restores the same workspace."
    ),
    response_model=ApiResponse[AccessTokenResponse],
    responses=AUTH_ERROR_RESPONSES,
)
async def select_tenant(
    payload: SelectTenantRequest, principal: PrincipalDep, auth: AuthServiceDep
) -> ApiResponse[AccessTokenResponse]:
    result = await auth.select_tenant(
        user=principal.user, tenant_id=payload.tenant_id, session_id=principal.session_id
    )
    return ok(result)


@router.get(
    "/sessions",
    summary="List active sessions",
    description=(
        "The caller's live sessions, for device management. Carries no token "
        "material — only the metadata captured when each session was created."
    ),
    response_model=ApiResponse[list[SessionRead]],
    responses=AUTH_ERROR_RESPONSES,
)
async def list_sessions(
    principal: PrincipalDep, auth: AuthServiceDep
) -> ApiResponse[list[SessionRead]]:
    rows = await auth.list_sessions(principal.user_id)
    return ok(
        [
            SessionRead(
                id=row.id,
                user_agent=row.user_agent,
                ip_address=str(row.ip_address) if row.ip_address else None,
                active_tenant_id=row.active_tenant_id,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                expires_at=row.expires_at,
                is_current=row.id == principal.session_id,
            )
            for row in rows
        ]
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Revoke a session",
    description=(
        "Signs one device out by revoking its token family. Returns a zero count "
        "for an unknown id rather than confirming whether it exists."
    ),
    response_model=ApiResponse[dict],
    responses=AUTH_ERROR_RESPONSES,
)
async def revoke_session(
    principal: PrincipalDep,
    auth: AuthServiceDep,
    session_id: Annotated[UUID, Path(description="Session to revoke")],
) -> ApiResponse[dict]:
    revoked = await auth.revoke_session(user_id=principal.user_id, session_id=session_id)
    return ok({"revoked_sessions": revoked})

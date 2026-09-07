"""Authentication service.

Holds the login, rotation, revocation and tenant-selection flows. Notable
decisions, each of which exists to close a specific hole:

* **No user enumeration.** An unknown email and a wrong password produce the
  same error *and* the same amount of work: the unknown-email path still runs
  a hash verification against a dummy hash, so response timing does not reveal
  which addresses are registered.
* **Refresh reuse kills the family.** Presenting an already-rotated token means
  the token leaked, so every descendant of that login is revoked rather than
  just the replayed row.
* **``tid`` is never trusted.** The tenant a token claims is re-validated
  against ``tenant_memberships`` on every use, so a stale or forged claim is
  worthless.
* **Audit writes need a tenant.** ``audit_logs`` is tenant-owned, so an event
  that happens before a workspace is selected (a failed login, a registration
  with no workspace) is written to the application log only. That is a
  deliberate consequence of keeping the audit trail tenant-scoped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.context import get_request_context
from app.core.enums import MembershipStatus, TenantStatus
from app.core.exceptions import (
    AuthenticationError,
    DuplicateResourceError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    TenantAccessError,
    TokenExpiredError,
    TokenRevokedError,
    ValidationError,
)
from app.core.ids import uuid7
from app.core.security.jwt import JwtService
from app.core.security.password import PasswordHasher
from app.core.security.refresh_tokens import generate_refresh_token, hash_refresh_token
from app.db.session import TenantAwareSession
from app.models.sessions import RefreshSession
from app.models.tenants import Tenant, TenantMembership
from app.models.users import User
from app.repositories.rbac import EffectivePermissionRepository
from app.repositories.sessions import RefreshSessionRepository
from app.repositories.tenants import MembershipRepository, TenantRepositoryGlobal
from app.repositories.users import UserRepository
from app.schemas.auth import AccessTokenResponse, TokenPair

logger = get_logger(__name__)

#: Revocation reasons recorded on a session row, for security review.
REASON_ROTATED = "rotated"
REASON_LOGOUT = "logout"
REASON_REUSE_DETECTED = "reuse_detected"
REASON_PASSWORD_CHANGED = "password_changed"
REASON_REVOKED_BY_USER = "revoked_by_user"


class AuthService:
    """Login, token rotation, revocation and workspace selection."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        users: UserRepository,
        tenants: TenantRepositoryGlobal,
        memberships: MembershipRepository,
        sessions: RefreshSessionRepository,
        permissions: EffectivePermissionRepository,
        password_hasher: PasswordHasher,
        jwt_service: JwtService,
        audit: AuditService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._users = users
        self._tenants = tenants
        self._memberships = memberships
        self._sessions = sessions
        self._permissions = permissions
        self._hasher = password_hasher
        self._jwt = jwt_service
        self._audit = audit
        self._settings = settings

    # ------------------------------------------------------------ register --

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        """Create an account.

        Strength is validated here (not only in the schema) because this layer
        knows the user's name and email and can reject a password derived from
        them.
        """
        normalized = email.strip().lower()
        if await self._users.email_exists(normalized):
            # Registration is the one place where "this email exists" has to be
            # sayable: the alternative is silently doing nothing.
            raise DuplicateResourceError(
                "An account with this email address already exists",
                code="EMAIL_ALREADY_REGISTERED",
            )

        self._hasher.validate_strength(
            password,
            personal_data=tuple(value for value in (normalized, first_name, last_name) if value),
        )
        user = User(
            email=normalized,
            password_hash=self._hasher.hash(password),
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        self._session.add(user)
        await self._session.flush()
        logger.info("user registered", extra={"user_id": str(user.id)})
        return user

    # --------------------------------------------------------------- login --

    async def authenticate(self, *, email: str, password: str) -> User:
        """Verify credentials, or raise an indistinguishable error."""
        normalized = email.strip().lower()
        user = await self._users.get_by_email(normalized)

        if user is None:
            # Spend comparable time so an unregistered address cannot be
            # identified by a faster rejection.
            self._hasher.dummy_verify()
            logger.info("login failed: unknown email")
            raise InvalidCredentialsError()

        if not self._hasher.verify(password, user.password_hash):
            logger.info("login failed: bad password", extra={"user_id": str(user.id)})
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        # Transparent upgrade when the cost parameters have been raised.
        if self._hasher.needs_rehash(user.password_hash):
            user.password_hash = self._hasher.hash(password)
            logger.info("password hash upgraded", extra={"user_id": str(user.id)})

        user.last_login_at = datetime.now(UTC)
        await self._session.flush()
        return user

    async def login(
        self, *, email: str, password: str, requested_tenant_id: UUID | None
    ) -> TokenPair:
        """Authenticate and issue a token pair."""
        user = await self.authenticate(email=email, password=password)
        tenant = await self._resolve_login_tenant(user, requested_tenant_id)
        tenant_id = tenant.id if tenant else None

        session_row, refresh_token = await self._start_session(user, tenant_id=tenant_id)
        pair = self._issue_pair(
            user=user,
            session_row=session_row,
            refresh_token=refresh_token,
            tenant_id=tenant_id,
        )

        if tenant_id is not None:
            await self._session.set_tenant_context(tenant_id=tenant_id, user_id=user.id)
            await self._audit.record(
                AuditAction.USER_LOGIN,
                resource_type="user",
                resource_id=user.id,
                user_id=user.id,
                metadata={
                    "email": user.email,
                    "session_id": str(session_row.id),
                    "tenant_id": str(tenant_id),
                },
            )
        else:
            # No workspace selected yet, so there is no tenant-owned audit table
            # to write to. Recorded in the application log instead.
            logger.info("login succeeded without a workspace", extra={"user_id": str(user.id)})
        return pair

    async def _resolve_login_tenant(
        self, user: User, requested_tenant_id: UUID | None
    ) -> Tenant | None:
        """Pick the active workspace for a new session.

        An explicitly requested workspace is validated against membership. With
        no request, a user who belongs to exactly one workspace gets it
        automatically — convenient, and safe because it is their own
        membership. A user in several must choose, so a token is never
        implicitly scoped to a workspace they did not name.
        """
        if requested_tenant_id is not None:
            return await self._require_membership(user.id, requested_tenant_id)

        memberships = [
            membership
            for membership in await self._memberships.list_for_user(user.id)
            if membership.status == MembershipStatus.ACTIVE.value
        ]
        if len(memberships) != 1:
            return None
        tenant = await self._tenants.get_by_id(memberships[0].tenant_id)
        return tenant if tenant and tenant.is_active else None

    async def _require_membership(self, user_id: UUID, tenant_id: UUID) -> Tenant:
        """Validate that ``user_id`` may act in ``tenant_id``.

        The single choke point for tenant authorisation. Every path that scopes
        a token or a request to a workspace goes through here.
        """
        membership = await self._memberships.get_active_for_user_and_tenant(
            user_id=user_id, tenant_id=tenant_id
        )
        if membership is None:
            logger.warning(
                "tenant access denied",
                extra={"user_id": str(user_id), "requested_tenant_id": str(tenant_id)},
            )
            raise TenantAccessError()

        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None or not tenant.is_active:
            raise TenantAccessError(
                "This workspace is not active",
                code="TENANT_INACTIVE",
                details={"status": tenant.status if tenant else TenantStatus.ARCHIVED.value},
            )
        return tenant

    # --------------------------------------------------------------- tokens --

    async def _start_session(
        self, user: User, *, tenant_id: UUID | None
    ) -> tuple[RefreshSession, str]:
        """Open a new token family for this login."""
        context = get_request_context()
        raw_token = generate_refresh_token()
        session_row = RefreshSession(
            user_id=user.id,
            family_id=uuid7(),
            token_hash=hash_refresh_token(raw_token),
            active_tenant_id=tenant_id,
            user_agent=(context.user_agent or None),
            ip_address=context.client_ip,
            expires_at=datetime.now(UTC)
            + timedelta(days=self._settings.jwt_refresh_token_expire_days),
            last_used_at=datetime.now(UTC),
        )
        self._session.add(session_row)
        await self._session.flush()
        return session_row, raw_token

    def _issue_pair(
        self,
        *,
        user: User,
        session_row: RefreshSession,
        refresh_token: str,
        tenant_id: UUID | None,
    ) -> TokenPair:
        access_token, claims = self._jwt.create_access_token(
            user_id=user.id, session_id=session_row.id, tenant_id=tenant_id
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self._jwt.access_token_ttl.total_seconds()),
            expires_at=claims.expires_at,
            active_tenant_id=tenant_id,
        )

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        """Rotate a refresh token, detecting replay.

        The old row is revoked and a new one is inserted in the same family, so
        exactly one token per family is ever valid.
        """
        token_hash = hash_refresh_token(refresh_token)
        session_row = await self._sessions.get_by_token_hash(token_hash)
        if session_row is None:
            logger.warning("refresh rejected: unknown token")
            raise InvalidTokenError("Refresh token is not recognised")

        if session_row.revoked:
            # Replay of a rotated token: the token leaked. Kill the lineage.
            revoked = await self._sessions.revoke_family(
                session_row.family_id, reason=REASON_REUSE_DETECTED
            )
            logger.warning(
                "refresh token reuse detected; family revoked",
                extra={
                    "user_id": str(session_row.user_id),
                    "family_id": str(session_row.family_id),
                    "revoked_count": revoked,
                },
            )
            await self._try_audit_for_tenant(
                session_row.active_tenant_id,
                session_row.user_id,
                AuditAction.TOKEN_REUSE_DETECTED,
                resource_id=session_row.id,
                metadata={
                    "family_id": str(session_row.family_id),
                    "revoked_count": revoked,
                },
            )
            raise TokenRevokedError("This refresh token has already been used")

        if session_row.expires_at <= datetime.now(UTC):
            raise TokenExpiredError("Refresh token has expired")

        user = await self._users.get_by_id(session_row.user_id)
        if user is None or not user.is_active:
            await self._sessions.revoke_family(session_row.family_id, reason=REASON_LOGOUT)
            raise InactiveUserError()

        # Re-validate the remembered workspace: membership may have been
        # revoked since the token was issued, and a token must never outlive
        # the access it represents.
        tenant_id = session_row.active_tenant_id
        if tenant_id is not None:
            membership = await self._memberships.get_active_for_user_and_tenant(
                user_id=user.id, tenant_id=tenant_id
            )
            if membership is None:
                logger.info(
                    "refresh dropped stale workspace scope",
                    extra={"user_id": str(user.id), "tenant_id": str(tenant_id)},
                )
                tenant_id = None

        await self._sessions.revoke(session_row, reason=REASON_ROTATED)
        context = get_request_context()
        raw_token = generate_refresh_token()
        rotated = RefreshSession(
            user_id=user.id,
            family_id=session_row.family_id,
            token_hash=hash_refresh_token(raw_token),
            active_tenant_id=tenant_id,
            user_agent=(context.user_agent or session_row.user_agent),
            ip_address=context.client_ip or session_row.ip_address,
            expires_at=datetime.now(UTC)
            + timedelta(days=self._settings.jwt_refresh_token_expire_days),
            last_used_at=datetime.now(UTC),
        )
        self._session.add(rotated)
        await self._session.flush()

        pair = self._issue_pair(
            user=user, session_row=rotated, refresh_token=raw_token, tenant_id=tenant_id
        )
        await self._try_audit_for_tenant(
            tenant_id,
            user.id,
            AuditAction.TOKEN_REFRESHED,
            resource_id=rotated.id,
            metadata={"session_id": str(rotated.id), "family_id": str(rotated.family_id)},
        )
        return pair

    async def logout(
        self,
        *,
        user_id: UUID,
        session_id: UUID | None = None,
        refresh_token: str | None = None,
        all_sessions: bool = False,
    ) -> int:
        """Revoke sessions. Returns how many rows were revoked."""
        if all_sessions:
            revoked = await self._sessions.revoke_all_for_user(user_id, reason=REASON_LOGOUT)
        elif refresh_token:
            session_row = await self._sessions.get_by_token_hash(hash_refresh_token(refresh_token))
            # Revoking the whole family, not just this row: a logout should not
            # leave an already-rotated sibling usable.
            if session_row is None or session_row.user_id != user_id:
                # Idempotent and non-revealing: logging out an unknown token is
                # not an error and must not confirm whether it existed.
                revoked = 0
            else:
                revoked = await self._sessions.revoke_family(
                    session_row.family_id, reason=REASON_LOGOUT
                )
        elif session_id is not None:
            session_row = await self._sessions.get_by_id_for_user(session_id, user_id)
            revoked = (
                await self._sessions.revoke_family(session_row.family_id, reason=REASON_LOGOUT)
                if session_row
                else 0
            )
        else:
            raise ValidationError(
                "Provide a refresh token, a session id, or set all_sessions",
                code="LOGOUT_TARGET_REQUIRED",
            )

        logger.info("logout", extra={"user_id": str(user_id), "revoked_count": revoked})
        return revoked

    async def revoke_session(self, *, user_id: UUID, session_id: UUID) -> int:
        """Revoke one device's session family."""
        session_row = await self._sessions.get_by_id_for_user(session_id, user_id)
        if session_row is None:
            # Same reasoning as logout: do not confirm another user's session id.
            return 0
        return await self._sessions.revoke_family(
            session_row.family_id, reason=REASON_REVOKED_BY_USER
        )

    async def list_sessions(self, user_id: UUID) -> list[RefreshSession]:
        return await self._sessions.list_active_for_user(user_id)

    # ------------------------------------------------------ tenant selection --

    async def select_tenant(
        self, *, user: User, tenant_id: UUID, session_id: UUID
    ) -> AccessTokenResponse:
        """Switch the active workspace and mint a scoped access token.

        Only the access token is reissued. Switching workspace is not a
        re-authentication, so rotating the refresh token here would multiply
        live tokens for no security benefit.
        """
        tenant = await self._require_membership(user.id, tenant_id)

        session_row = await self._sessions.get_by_id_for_user(session_id, user.id)
        if session_row is None or session_row.revoked:
            raise AuthenticationError("Session is no longer valid")
        # Remembered so a later refresh restores the same workspace.
        session_row.active_tenant_id = tenant.id
        await self._session.flush()

        access_token, claims = self._jwt.create_access_token(
            user_id=user.id, session_id=session_row.id, tenant_id=tenant.id
        )
        await self._session.set_tenant_context(tenant_id=tenant.id, user_id=user.id)
        await self._audit.record(
            AuditAction.TENANT_SELECTED,
            resource_type="tenant",
            resource_id=tenant.id,
            user_id=user.id,
            metadata={"tenant_id": str(tenant.id), "tenant_slug": tenant.slug},
        )
        return AccessTokenResponse(
            access_token=access_token,
            expires_in=int(self._jwt.access_token_ttl.total_seconds()),
            expires_at=claims.expires_at,
            active_tenant_id=tenant.id,
        )

    # ------------------------------------------------------------ passwords --

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool,
        current_session_id: UUID | None,
    ) -> int:
        """Change the caller's password.

        The current password is required even though the caller is
        authenticated: a stolen access token must not be enough to take over
        the account.
        """
        if not self._hasher.verify(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")

        self._hasher.validate_strength(
            new_password,
            personal_data=tuple(
                value for value in (user.email, user.first_name, user.last_name) if value
            ),
        )
        if self._hasher.verify(new_password, user.password_hash):
            raise ValidationError(
                "New password must differ from the current one", code="PASSWORD_UNCHANGED"
            )

        user.password_hash = self._hasher.hash(new_password)
        await self._session.flush()

        revoked = 0
        if revoke_other_sessions:
            revoked = await self._sessions.revoke_all_for_user(
                user.id, reason=REASON_PASSWORD_CHANGED
            )
            # The caller keeps working: only *other* devices are signed out.
            if current_session_id is not None:
                current = await self._sessions.get_by_id_for_user(current_session_id, user.id)
                if current is not None:
                    current.revoked = False
                    current.revoked_reason = None
                    current.revoked_at = None
                    revoked = max(0, revoked - 1)
                    await self._session.flush()

        logger.info(
            "password changed",
            extra={"user_id": str(user.id), "revoked_sessions": revoked},
        )
        return revoked

    # -------------------------------------------------------------- helpers --

    async def effective_permissions(self, *, user_id: UUID, tenant_id: UUID) -> frozenset[str]:
        return await self._permissions.codes_for_user_in_tenant(
            user_id=user_id, tenant_id=tenant_id
        )

    async def memberships_for_user(self, user_id: UUID) -> list[TenantMembership]:
        return await self._memberships.list_for_user(user_id)

    async def _try_audit_for_tenant(
        self,
        tenant_id: UUID | None,
        user_id: UUID,
        action: AuditAction,
        *,
        resource_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Write an audit row when a workspace context exists.

        ``audit_logs`` is tenant-owned, so pre-tenant events cannot be stored
        there. Rather than weaken the table's tenant scoping, those events are
        left to the application log.
        """
        if tenant_id is None:
            logger.info("auth event outside a workspace: %s", action.value)
            return
        await self._session.set_tenant_context(tenant_id=tenant_id, user_id=user_id)
        await self._audit.record(
            action,
            resource_type="session",
            resource_id=resource_id,
            user_id=user_id,
            metadata=metadata,
        )

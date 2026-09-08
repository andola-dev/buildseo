"""Application-level exception hierarchy.

Services and repositories raise these; a single set of handlers
(:mod:`app.core.error_handlers`) maps them onto HTTP status codes and the error
envelope. Routers never raise ``HTTPException`` for a domain outcome, so the
same services can be reused by workers and CLI scripts.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every expected, non-bug error condition.

    ``code`` is a stable, machine-readable identifier that clients may branch
    on. ``message`` is safe to return to the caller — it must never embed
    internal details such as SQL, stack frames or secrets.
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details: dict[str, Any] = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# --------------------------------------------------------------------------- #
# 401 / 403
# --------------------------------------------------------------------------- #


class AuthenticationError(AppError):
    """Caller could not be authenticated (missing/invalid/expired credentials)."""

    status_code = 401
    code = "AUTHENTICATION_FAILED"
    message = "Authentication failed"


class InvalidCredentialsError(AuthenticationError):
    """Deliberately indistinguishable for unknown email and wrong password."""

    code = "INVALID_CREDENTIALS"
    message = "Incorrect email or password"


class TokenExpiredError(AuthenticationError):
    code = "TOKEN_EXPIRED"
    message = "Token has expired"


class TokenRevokedError(AuthenticationError):
    code = "TOKEN_REVOKED"
    message = "Token has been revoked"


class InvalidTokenError(AuthenticationError):
    code = "INVALID_TOKEN"
    message = "Token is invalid"


class InactiveUserError(AuthenticationError):
    status_code = 403
    code = "USER_INACTIVE"
    message = "User account is not active"


class AuthorizationError(AppError):
    """Authenticated, but lacking the required permission."""

    status_code = 403
    code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action"

    @classmethod
    def for_permission(cls, permission: str) -> AuthorizationError:
        return cls(
            f"Missing required permission: {permission}",
            details={"required_permission": permission},
        )


class TenantAccessError(AppError):
    """The user is not an active member of the requested tenant."""

    status_code = 403
    code = "TENANT_ACCESS_DENIED"
    message = "You do not have access to this tenant"


class TenantContextMissingError(AppError):
    """A tenant-scoped operation was attempted without an active tenant."""

    status_code = 400
    code = "TENANT_CONTEXT_REQUIRED"
    message = "An active tenant must be selected for this request"


# --------------------------------------------------------------------------- #
# 404 / 409 / 422
# --------------------------------------------------------------------------- #


class ResourceNotFoundError(AppError):
    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    message = "Resource was not found"

    @classmethod
    def for_resource(cls, resource: str, identifier: Any = None) -> ResourceNotFoundError:
        """Build a not-found error without leaking whether the id exists elsewhere.

        Cross-tenant lookups deliberately surface as 404 rather than 403 so a
        caller cannot probe another tenant's identifier space.
        """
        human = resource.replace("_", " ").capitalize()
        return cls(
            f"{human} was not found",
            code=f"{resource.upper()}_NOT_FOUND",
            details={"resource": resource, "id": str(identifier)} if identifier else None,
        )


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource"


class DuplicateResourceError(ConflictError):
    code = "DUPLICATE_RESOURCE"
    message = "A resource with these values already exists"


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"
    message = "This idempotency key was already used with a different request body"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Request validation failed"


class InvalidSortFieldError(ValidationError, ValueError):
    """A client asked to sort by a field outside the resource's allow-list.

    Deliberately inherits from ``ValueError`` as well. The check happens deep
    in ``resolve_sort``, called from the repository rather than from a request
    dependency, so the natural thing for that function to raise is a
    ``ValueError`` — and callers outside the API (workers, scripts, unit tests)
    reasonably catch one.

    Inheriting ``AppError`` as well is what keeps that from costing a 500:
    Starlette resolves a handler by walking ``type(exc).__mro__``, and
    ``AppError`` sits ahead of ``ValueError`` in this class's MRO, so
    ``app_error_handler`` claims it and returns the intended 422. The
    alternative — registering a handler for ``ValueError`` itself — would
    reclassify *every* unexpected ``ValueError`` in the stack as a client
    error and echo its text back, hiding real defects behind a 422.
    """

    code = "INVALID_SORT_FIELD"

    @classmethod
    def for_field(cls, requested: str, *, allowed: frozenset[str]) -> InvalidSortFieldError:
        """Build the error, naming the fields the caller may actually use."""
        return cls(
            f"'{requested}' is not a sortable field",
            details={"field": requested, "allowed": sorted(allowed)},
        )


class BusinessRuleError(AppError):
    """A domain invariant was violated (distinct from schema validation)."""

    status_code = 422
    code = "BUSINESS_RULE_VIOLATION"
    message = "The request violates a business rule"


class PaidPlacementNotAllowedError(BusinessRuleError):
    """MVP rule 1/2: only FREE listings may enter the submission workflow."""

    code = "PAID_PLACEMENT_NOT_ALLOWED"
    message = (
        "Only publishers with pricing_type=FREE may enter the submission workflow. "
        "Paid placements are out of scope for this platform."
    )


class SubmissionError(AppError):
    status_code = 409
    code = "SUBMISSION_ERROR"
    message = "The submission could not be processed"


class InvalidStateTransitionError(SubmissionError):
    code = "INVALID_STATE_TRANSITION"
    message = "That status transition is not allowed"

    @classmethod
    def between(cls, entity: str, current: str, target: str) -> InvalidStateTransitionError:
        return cls(
            f"Cannot transition {entity} from {current} to {target}",
            details={"entity": entity, "from": current, "to": target},
        )


# --------------------------------------------------------------------------- #
# Credentials / providers
# --------------------------------------------------------------------------- #


class CredentialError(AppError):
    status_code = 422
    code = "CREDENTIAL_ERROR"
    message = "The credential could not be processed"


class CredentialDecryptionError(CredentialError):
    status_code = 500
    code = "CREDENTIAL_DECRYPTION_FAILED"
    message = "Stored credential could not be decrypted"


class CredentialNotConfiguredError(CredentialError):
    status_code = 422
    code = "CREDENTIAL_NOT_CONFIGURED"
    message = "No credential is configured for this provider"


class ProviderError(AppError):
    """An external provider failed. Never carries the provider's raw response."""

    status_code = 502
    code = "PROVIDER_ERROR"
    message = "An external provider returned an error"


class ProviderUnavailableError(ProviderError):
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"
    message = "An external provider is temporarily unavailable"


class ProviderNotSupportedError(AppError):
    status_code = 422
    code = "PROVIDER_NOT_SUPPORTED"
    message = "That provider is not supported"


class ProviderTimeoutError(ProviderError):
    status_code = 504
    code = "PROVIDER_TIMEOUT"
    message = "An external provider did not respond in time"


class ResponseTooLargeError(ProviderError):
    status_code = 502
    code = "RESPONSE_TOO_LARGE"
    message = "An external response exceeded the maximum allowed size"


# --------------------------------------------------------------------------- #
# Throttling
# --------------------------------------------------------------------------- #


class RateLimitExceededError(AppError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds

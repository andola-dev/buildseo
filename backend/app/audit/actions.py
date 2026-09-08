"""Audited action codes and their metadata allow-lists.

Every audited action declares exactly which metadata fields may be recorded.
That is the mechanism that keeps secrets out of the audit trail: the service
filters a caller's metadata dict through the action's allow-list, so passing a
whole request body records only the permitted keys and drops the rest — rather
than relying on every call site to remember what is safe.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from app.config.logging import get_logger, scrub_value

logger = get_logger(__name__)

#: JSONB has no size limit, but an audit row is not a data store. Long values
#: are truncated so a stray blob cannot bloat the table.
_MAX_VALUE_LENGTH = 500
_MAX_LIST_ITEMS = 50


class AuditAction(StrEnum):
    """Stable action codes. Never renamed — a trail must stay queryable."""

    # --- authentication and session ---------------------------------------- #
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGIN = "USER_LOGIN"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    USER_LOGOUT = "USER_LOGOUT"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_REUSE_DETECTED = "TOKEN_REUSE_DETECTED"
    SESSION_REVOKED = "SESSION_REVOKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    TENANT_SELECTED = "TENANT_SELECTED"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # --- tenant and membership --------------------------------------------- #
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_UPDATED = "TENANT_UPDATED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_UPDATED = "MEMBER_UPDATED"
    MEMBER_REMOVED = "MEMBER_REMOVED"

    # --- RBAC ---------------------------------------------------------------- #
    ROLE_CREATED = "ROLE_CREATED"
    ROLE_UPDATED = "ROLE_UPDATED"
    ROLE_DELETED = "ROLE_DELETED"

    # --- domain -------------------------------------------------------------- #
    CLIENT_WEBSITE_CREATED = "CLIENT_WEBSITE_CREATED"
    CLIENT_WEBSITE_UPDATED = "CLIENT_WEBSITE_UPDATED"
    CLIENT_WEBSITE_DELETED = "CLIENT_WEBSITE_DELETED"
    CAMPAIGN_CREATED = "CAMPAIGN_CREATED"
    CAMPAIGN_UPDATED = "CAMPAIGN_UPDATED"
    CAMPAIGN_DELETED = "CAMPAIGN_DELETED"
    PUBLISHER_CREATED = "PUBLISHER_CREATED"
    PUBLISHER_UPDATED = "PUBLISHER_UPDATED"
    PUBLISHER_DELETED = "PUBLISHER_DELETED"
    PUBLISHER_DISCOVERY_STARTED = "PUBLISHER_DISCOVERY_STARTED"
    PUBLISHER_DISCOVERY_COMPLETED = "PUBLISHER_DISCOVERY_COMPLETED"
    PUBLISHER_QUALIFIED = "PUBLISHER_QUALIFIED"
    OPPORTUNITY_CREATED = "OPPORTUNITY_CREATED"
    OPPORTUNITY_UPDATED = "OPPORTUNITY_UPDATED"
    OPPORTUNITY_QUALIFIED = "OPPORTUNITY_QUALIFIED"
    OPPORTUNITY_SELECTED = "OPPORTUNITY_SELECTED"
    OPPORTUNITY_REJECTED = "OPPORTUNITY_REJECTED"
    OPPORTUNITY_DELETED = "OPPORTUNITY_DELETED"
    SUBMISSION_CREATED = "SUBMISSION_CREATED"
    SUBMISSION_UPDATED = "SUBMISSION_UPDATED"
    SUBMISSION_APPROVED = "SUBMISSION_APPROVED"
    SUBMISSION_EXECUTED = "SUBMISSION_EXECUTED"
    SUBMISSION_VERIFIED = "SUBMISSION_VERIFIED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    SUBMISSION_DELETED = "SUBMISSION_DELETED"
    PAID_PLACEMENT_BLOCKED = "PAID_PLACEMENT_BLOCKED"

    # --- content and AI ------------------------------------------------------ #
    CONTENT_GENERATED = "CONTENT_GENERATED"
    CONTENT_REVIEWED = "CONTENT_REVIEWED"

    # --- BYOK ---------------------------------------------------------------- #
    CREDENTIAL_CREATED = "CREDENTIAL_CREATED"
    CREDENTIAL_UPDATED = "CREDENTIAL_UPDATED"
    CREDENTIAL_ROTATED = "CREDENTIAL_ROTATED"
    CREDENTIAL_VERIFIED = "CREDENTIAL_VERIFIED"
    CREDENTIAL_DELETED = "CREDENTIAL_DELETED"
    AI_CONFIG_UPDATED = "AI_CONFIG_UPDATED"

    # --- operations ---------------------------------------------------------- #
    JOB_ENQUEUED = "JOB_ENQUEUED"
    JOB_FAILED = "JOB_FAILED"


#: Fields permitted in every action's metadata.
_COMMON_FIELDS = frozenset({"reason", "source", "job_id"})

#: Per-action allow-lists. An action absent from this map records only
#: ``_COMMON_FIELDS``, so a new action defaults to recording almost nothing
#: rather than defaulting to recording everything.
METADATA_ALLOWLIST: Mapping[AuditAction, frozenset[str]] = MappingProxyType(
    {
        AuditAction.USER_REGISTERED: frozenset({"email", "tenant_created", "tenant_slug"}),
        AuditAction.USER_LOGIN: frozenset({"email", "session_id", "tenant_id"}),
        # Records that a login failed and for which address, never the attempted
        # password or any hint about which half was wrong.
        AuditAction.USER_LOGIN_FAILED: frozenset({"email", "failure"}),
        AuditAction.USER_LOGOUT: frozenset({"session_id", "all_sessions"}),
        AuditAction.TOKEN_REFRESHED: frozenset({"session_id", "family_id"}),
        AuditAction.TOKEN_REUSE_DETECTED: frozenset({"family_id", "revoked_count"}),
        AuditAction.SESSION_REVOKED: frozenset({"session_id", "revoked_count"}),
        AuditAction.PASSWORD_CHANGED: frozenset({"revoked_sessions"}),
        AuditAction.TENANT_SELECTED: frozenset({"tenant_id", "tenant_slug"}),
        AuditAction.TENANT_ACCESS_DENIED: frozenset({"requested_tenant_id"}),
        AuditAction.PERMISSION_DENIED: frozenset({"required_permission", "endpoint", "method"}),
        AuditAction.TENANT_CREATED: frozenset({"name", "slug"}),
        AuditAction.TENANT_UPDATED: frozenset({"changed_fields", "status"}),
        AuditAction.MEMBER_ADDED: frozenset({"user_id", "email", "role_slugs", "status"}),
        AuditAction.MEMBER_UPDATED: frozenset(
            {"user_id", "role_slugs", "status", "is_owner", "changed_fields"}
        ),
        AuditAction.MEMBER_REMOVED: frozenset({"user_id", "email"}),
        AuditAction.ROLE_CREATED: frozenset({"slug", "name", "permission_count"}),
        AuditAction.ROLE_UPDATED: frozenset({"slug", "name", "permission_count", "changed_fields"}),
        AuditAction.ROLE_DELETED: frozenset({"slug", "name"}),
        AuditAction.CLIENT_WEBSITE_CREATED: frozenset({"name", "normalized_domain"}),
        AuditAction.CLIENT_WEBSITE_UPDATED: frozenset({"changed_fields", "status"}),
        AuditAction.CLIENT_WEBSITE_DELETED: frozenset({"name", "normalized_domain"}),
        AuditAction.CAMPAIGN_CREATED: frozenset({"name", "client_website_id", "status"}),
        AuditAction.CAMPAIGN_UPDATED: frozenset({"changed_fields", "status"}),
        AuditAction.CAMPAIGN_DELETED: frozenset({"name"}),
        AuditAction.PUBLISHER_CREATED: frozenset(
            {"normalized_domain", "pricing_type", "category", "country", "discovery_run_id"}
        ),
        AuditAction.PUBLISHER_UPDATED: frozenset(
            {"changed_fields", "pricing_type", "status", "normalized_domain"}
        ),
        AuditAction.PUBLISHER_DELETED: frozenset({"normalized_domain"}),
        AuditAction.PUBLISHER_DISCOVERY_STARTED: frozenset(
            {"provider", "keywords", "country", "category", "limit", "campaign_id"}
        ),
        AuditAction.PUBLISHER_DISCOVERY_COMPLETED: frozenset(
            {"provider", "results_found", "publishers_created", "duplicates_skipped", "status"}
        ),
        AuditAction.PUBLISHER_QUALIFIED: frozenset(
            {
                "normalized_domain",
                "quality_score",
                "relevance_score",
                "spam_score",
                "authority_score",
                "recommended_status",
                "eligible_for_submission",
            }
        ),
        AuditAction.OPPORTUNITY_CREATED: frozenset(
            {"campaign_id", "publisher_id", "opportunity_type", "target_url"}
        ),
        AuditAction.OPPORTUNITY_UPDATED: frozenset({"changed_fields", "priority"}),
        AuditAction.OPPORTUNITY_QUALIFIED: frozenset({"qualification_score", "priority"}),
        AuditAction.OPPORTUNITY_SELECTED: frozenset({"campaign_id", "publisher_id", "priority"}),
        AuditAction.OPPORTUNITY_REJECTED: frozenset({"campaign_id", "publisher_id"}),
        AuditAction.OPPORTUNITY_DELETED: frozenset({"campaign_id", "publisher_id"}),
        AuditAction.SUBMISSION_CREATED: frozenset(
            {"campaign_id", "opportunity_id", "submission_method", "target_url"}
        ),
        AuditAction.SUBMISSION_UPDATED: frozenset({"changed_fields", "status"}),
        AuditAction.SUBMISSION_APPROVED: frozenset({"opportunity_id", "approved_by_user_id"}),
        AuditAction.SUBMISSION_EXECUTED: frozenset(
            {"opportunity_id", "submitted_url", "submission_method", "status"}
        ),
        AuditAction.SUBMISSION_VERIFIED: frozenset({"opportunity_id", "verified", "published_url"}),
        AuditAction.SUBMISSION_FAILED: frozenset({"opportunity_id", "failure_reason"}),
        AuditAction.SUBMISSION_DELETED: frozenset({"opportunity_id"}),
        AuditAction.PAID_PLACEMENT_BLOCKED: frozenset(
            {"publisher_id", "normalized_domain", "pricing_type", "opportunity_id"}
        ),
        # Records which model produced content and how much, never the prompt
        # or the generated text (the text lives in generated_contents).
        AuditAction.CONTENT_GENERATED: frozenset(
            {"opportunity_id", "ai_provider", "ai_model", "content_id", "field_count"}
        ),
        AuditAction.CONTENT_REVIEWED: frozenset({"content_id", "decision", "edited"}),
        # Never the key, the ciphertext, or the masked hint: provider, label
        # and status are all an auditor needs.
        AuditAction.CREDENTIAL_CREATED: frozenset({"provider", "provider_type", "label"}),
        AuditAction.CREDENTIAL_UPDATED: frozenset(
            {"provider", "label", "changed_fields", "status"}
        ),
        AuditAction.CREDENTIAL_ROTATED: frozenset({"provider", "label", "key_version"}),
        AuditAction.CREDENTIAL_VERIFIED: frozenset({"provider", "label", "verified", "error_code"}),
        AuditAction.CREDENTIAL_DELETED: frozenset({"provider", "label"}),
        AuditAction.AI_CONFIG_UPDATED: frozenset({"purpose", "provider", "model", "is_default"}),
        AuditAction.JOB_ENQUEUED: frozenset({"task_name", "job_id"}),
        AuditAction.JOB_FAILED: frozenset({"task_name", "job_id", "attempts", "error_code"}),
    }
)


def allowed_metadata_fields(action: AuditAction) -> frozenset[str]:
    """Fields recordable for ``action``, including the common ones."""
    return METADATA_ALLOWLIST.get(action, frozenset()) | _COMMON_FIELDS


def sanitize_metadata(action: AuditAction, metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only allow-listed keys, then scrub and truncate their values.

    Two layers on purpose: the allow-list decides *which* fields may exist, and
    the scrubber handles the case where a permitted field nonetheless contains
    something secret-shaped.
    """
    if not metadata:
        return {}
    allowed = allowed_metadata_fields(action)
    filtered = {key: value for key, value in metadata.items() if key in allowed}
    dropped = sorted(set(metadata) - allowed)
    if dropped:
        # Not an error: passing extra context is normal and dropping it is the
        # safe behaviour. Logged at debug so a developer can see why a field
        # never appeared in the trail.
        logger.debug("audit metadata fields dropped for %s: %s", action.value, ", ".join(dropped))
    return {key: _truncate(scrub_value(value)) for key, value in filtered.items()}


def _truncate(value: Any) -> Any:
    """Bound the size of a recorded value."""
    if isinstance(value, str) and len(value) > _MAX_VALUE_LENGTH:
        return value[:_MAX_VALUE_LENGTH] + "..."
    if isinstance(value, list):
        if len(value) > _MAX_LIST_ITEMS:
            return [_truncate(item) for item in value[:_MAX_LIST_ITEMS]] + ["..."]
        return [_truncate(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value

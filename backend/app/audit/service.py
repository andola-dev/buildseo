"""Audit log writing.

Two properties matter more than convenience here:

* **No secrets.** Metadata is filtered through the action's allow-list
  (:mod:`app.audit.actions`), so handing this service a whole request body
  records only the permitted keys. A password or API key in that body is
  dropped rather than persisted.
* **Append-only.** There is no update or delete method, and revision 0018
  revokes UPDATE and DELETE on ``audit_logs`` from the runtime role, so the
  application cannot rewrite its own history.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.audit.actions import AuditAction, sanitize_metadata
from app.config.logging import get_logger
from app.core.context import get_request_context
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRepository

logger = get_logger(__name__)


class AuditService:
    """Records security- and business-significant actions."""

    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    async def record(
        self,
        action: AuditAction,
        *,
        resource_type: str | None = None,
        resource_id: str | UUID | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: UUID | None = None,
    ) -> AuditLog:
        """Write one audit entry for the active tenant.

        ``user_id``, the client address, the user agent and the request id are
        taken from the ambient request context when not supplied, so call sites
        do not have to thread them through — and a worker gets the same shape
        because it binds the same context.
        """
        context = get_request_context()
        entry = self._repository.new(
            user_id=user_id if user_id is not None else context.user_id,
            action=action.value,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            audit_metadata=sanitize_metadata(action, metadata),
            ip_address=context.client_ip,
            user_agent=context.user_agent,
            request_id=context.request_id,
        )
        await self._repository.flush()
        logger.info(
            "audit: %s",
            action.value,
            extra={
                "audit_action": action.value,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id is not None else None,
            },
        )
        return entry

"""Audit log data access."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.sql.elements import ColumnElement

from app.models.audit import AuditLog
from app.repositories.base import TenantRepository


class AuditLogRepository(TenantRepository[AuditLog]):
    """Append-only.

    There is intentionally no update or delete method here, and revision 0018
    revokes UPDATE and DELETE on this table from the runtime role, so the
    application cannot rewrite its own history even if a future code path
    tried to.
    """

    model = AuditLog
    sortable_fields = frozenset({"created_at", "action", "resource_type"})
    default_sort = "created_at"

    def build_filters(
        self,
        *,
        action: str | None = None,
        actions: list[str] | None = None,
        user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if action:
            filters.append(AuditLog.action == action)
        if actions:
            filters.append(AuditLog.action.in_(actions))
        if user_id:
            filters.append(AuditLog.user_id == user_id)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            filters.append(AuditLog.resource_id == resource_id)
        if since:
            filters.append(AuditLog.created_at >= since)
        if until:
            filters.append(AuditLog.created_at < until)
        return filters

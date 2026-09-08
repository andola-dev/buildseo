"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata``, which is
what Alembic's ``env.py`` relies on for autogenerate and what the RLS
schema-audit test reflects over. ``ALL_MODELS`` gives that import an explicit,
lint-safe reason to exist.
"""

from __future__ import annotations

from app.db.base import Base
from app.models.ai_usage import AiUsageRecord
from app.models.audit import AuditLog
from app.models.campaigns import Campaign
from app.models.client_websites import ClientWebsite
from app.models.credentials import Credential, TenantAiConfig
from app.models.idempotency import IdempotencyKey
from app.models.jobs import Job
from app.models.opportunities import Opportunity
from app.models.publishers import DiscoveryRun, Publisher
from app.models.rbac import MembershipRole, Permission, Role, RolePermission
from app.models.sessions import RefreshSession
from app.models.submissions import GeneratedContent, Submission
from app.models.tenants import Tenant, TenantMembership
from app.models.users import User

#: Every mapped class, in dependency order.
ALL_MODELS: tuple[type[Base], ...] = (
    User,
    Tenant,
    TenantMembership,
    Permission,
    Role,
    RolePermission,
    MembershipRole,
    RefreshSession,
    ClientWebsite,
    Campaign,
    DiscoveryRun,
    Publisher,
    Opportunity,
    Submission,
    GeneratedContent,
    Credential,
    TenantAiConfig,
    AiUsageRecord,
    AuditLog,
    Job,
    IdempotencyKey,
)

#: Tables that must be covered by a Row-Level Security policy. Derived from the
#: schema itself (presence of a ``tenant_id`` column) rather than hand-listed,
#: so a new tenant-owned model cannot be forgotten: the RLS audit test compares
#: this set against ``pg_policies`` and ``pg_class.relforcerowsecurity``.
TENANT_OWNED_TABLES: frozenset[str] = frozenset(
    model.__tablename__
    for model in ALL_MODELS
    if "tenant_id" in model.__table__.columns  # type: ignore[attr-defined]
)

#: Global identity tables that intentionally carry no ``tenant_id``. See
#: docs/ARCHITECTURE.md §5.5 for why each is excluded from RLS.
GLOBAL_TABLES: frozenset[str] = frozenset({"users", "tenants", "permissions", "refresh_sessions"})

__all__ = [
    "ALL_MODELS",
    "GLOBAL_TABLES",
    "TENANT_OWNED_TABLES",
    "AiUsageRecord",
    "AuditLog",
    "Campaign",
    "ClientWebsite",
    "Credential",
    "DiscoveryRun",
    "GeneratedContent",
    "IdempotencyKey",
    "Job",
    "MembershipRole",
    "Opportunity",
    "Permission",
    "Publisher",
    "RefreshSession",
    "Role",
    "RolePermission",
    "Submission",
    "Tenant",
    "TenantAiConfig",
    "TenantMembership",
    "User",
]

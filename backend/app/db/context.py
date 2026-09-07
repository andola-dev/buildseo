"""PostgreSQL tenant context (the RLS handshake).

Row-Level Security policies compare ``tenant_id`` against
``app.current_tenant_id``. This module is the only place that sets those
settings, and it does so with three deliberate properties:

1. **Transaction-local.** ``set_config(..., is_local => true)`` makes PostgreSQL
   discard the value when the transaction ends. A pooled connection handed to
   the next request therefore carries no tenant — the single most important
   property for avoiding cross-tenant leakage under connection pooling.
2. **Parameterised.** The tenant id travels as a bind parameter, never string
   interpolation, so it cannot be used to inject SQL even though ``set_config``
   requires dynamic SQL.
3. **Server-derived.** Callers pass a tenant id that has already been checked
   against ``tenant_memberships``; nothing here trusts client input.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

TENANT_SETTING: Final = "app.current_tenant_id"
USER_SETTING: Final = "app.current_user_id"

#: ``is_local => true`` scopes both settings to the current transaction.
_SET_CONTEXT_SQL = text(
    "SELECT set_config(:tenant_setting, :tenant_id, true), "
    "       set_config(:user_setting, :user_id, true)"
)

_READ_CONTEXT_SQL = text(
    "SELECT nullif(current_setting(:tenant_setting, true), '') AS tenant_id, "
    "       nullif(current_setting(:user_setting, true), '') AS user_id"
)


async def apply_tenant_context(
    executor: AsyncSession | AsyncConnection,
    *,
    tenant_id: UUID | None,
    user_id: UUID | None,
) -> None:
    """Set (or clear) the tenant/user context for the current transaction.

    Passing ``None`` writes an empty string, which the ``app_current_*``
    SQL helpers turn back into ``NULL``. A ``NULL`` tenant makes every RLS
    predicate ``NULL`` — i.e. false — so an unscoped transaction sees nothing
    rather than everything. Default deny.
    """
    await executor.execute(
        _SET_CONTEXT_SQL,
        {
            "tenant_setting": TENANT_SETTING,
            "tenant_id": str(tenant_id) if tenant_id else "",
            "user_setting": USER_SETTING,
            "user_id": str(user_id) if user_id else "",
        },
    )


async def read_tenant_context(
    executor: AsyncSession | AsyncConnection,
) -> tuple[UUID | None, UUID | None]:
    """Read back what PostgreSQL currently considers the active context.

    Used by the RLS test-suite and the readiness probe to assert that the
    handshake actually took effect, rather than trusting the application's
    own bookkeeping.
    """
    row = (
        await executor.execute(
            _READ_CONTEXT_SQL, {"tenant_setting": TENANT_SETTING, "user_setting": USER_SETTING}
        )
    ).one()
    tenant_raw, user_raw = row
    return (
        UUID(tenant_raw) if tenant_raw else None,
        UUID(user_raw) if user_raw else None,
    )


async def clear_tenant_context(executor: AsyncSession | AsyncConnection) -> None:
    """Explicitly drop the context. Belt-and-braces alongside ``SET LOCAL``."""
    await apply_tenant_context(executor, tenant_id=None, user_id=None)

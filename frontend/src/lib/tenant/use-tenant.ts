"use client";

/**
 * The active-workspace slice of the session (spec §9).
 *
 * Workspace state is owned by `AuthProvider` because the backend's access token
 * is workspace-scoped — see the note at the top of `auth-provider.tsx`. This
 * hook is the interface feature code uses; nothing outside it needs to know
 * where the state lives.
 */

import { useAuthContext } from "@/lib/auth/auth-provider";

export function useTenant() {
  const {
    tenants,
    activeTenantId,
    activeTenant,
    tenantVersion,
    switchingTenant,
    switchTenant,
  } = useAuthContext();

  return {
    tenants,
    activeTenantId,
    activeTenant,
    tenantVersion,
    switchingTenant,
    switchTenant,
  };
}

/**
 * The active workspace id for a query that cannot run without one.
 *
 * Returns `null` while the session is still resolving; callers pass this
 * straight into `enabled: Boolean(tenantId)` so no request is made without a
 * workspace, which the backend would reject with `TENANT_CONTEXT_REQUIRED`.
 */
export function useTenantId(): string | null {
  return useAuthContext().activeTenantId;
}

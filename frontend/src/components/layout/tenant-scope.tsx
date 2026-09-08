"use client";

import { useTenant } from "@/lib/tenant/use-tenant";

/**
 * Discards tenant-scoped component state on a workspace switch (spec §49).
 *
 * Removing the cache entries is not enough on its own: a table's selected rows,
 * an open dialog or a half-filled wizard live in React state, and those would
 * otherwise survive the switch and be applied to the new workspace. Changing
 * the `key` unmounts the subtree, which is the only reliable way to clear all
 * of it at once.
 */
export function TenantScope({ children }: { children: React.ReactNode }) {
  const { activeTenantId, tenantVersion } = useTenant();

  return <div key={`${activeTenantId ?? "none"}:${tenantVersion}`}>{children}</div>;
}

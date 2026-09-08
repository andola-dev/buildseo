"use client";

/**
 * Frontend permission checks (spec §35).
 *
 * These decide what the interface *offers*. They are not security: the
 * permission set comes from the backend, and the backend enforces every rule
 * again on the request itself. Hiding a button prevents a confusing 403, it
 * does not prevent the action.
 */

import { useCallback, useMemo } from "react";

import { useAuthContext } from "@/lib/auth/auth-provider";

/**
 * Match a permission against a granted set, honouring wildcards.
 *
 * The backend may grant `*` or `publisher.*` for an owner-style role, so those
 * are understood here rather than requiring every code to be listed.
 */
export function matchesPermission(
  granted: ReadonlySet<string>,
  required: string,
): boolean {
  if (granted.has("*")) return true;
  if (granted.has(required)) return true;

  const separator = required.indexOf(".");
  if (separator > 0) {
    const resource = required.slice(0, separator);
    if (granted.has(`${resource}.*`)) return true;
  }

  return false;
}

export function usePermissions() {
  const { permissions } = useAuthContext();

  const can = useCallback(
    (permission: string | undefined | null): boolean => {
      if (!permission) return true;
      return matchesPermission(permissions, permission);
    },
    [permissions],
  );

  const canAny = useCallback(
    (required: readonly string[]): boolean =>
      required.length === 0 || required.some((permission) => matchesPermission(permissions, permission)),
    [permissions],
  );

  const canAll = useCallback(
    (required: readonly string[]): boolean =>
      required.every((permission) => matchesPermission(permissions, permission)),
    [permissions],
  );

  return useMemo(
    () => ({ can, canAny, canAll, permissions }),
    [can, canAny, canAll, permissions],
  );
}

/** Single-permission convenience: `const canCreate = usePermission("campaign.create")`. */
export function usePermission(permission: string | undefined | null): boolean {
  const { can } = usePermissions();
  return can(permission);
}

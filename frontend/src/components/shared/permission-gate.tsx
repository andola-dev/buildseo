"use client";

import { usePermissions } from "@/lib/permissions/use-permissions";

interface PermissionGateProps {
  /** A single permission code, or several. */
  permission?: string;
  anyOf?: readonly string[];
  allOf?: readonly string[];
  /**
   * `hide` removes the children; `disable` renders them inside a container that
   * blocks pointer input and dims them, for cases where the action should stay
   * visible so the user knows it exists.
   */
  mode?: "hide" | "disable";
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Show an action only when the backend granted the permission (spec §35).
 *
 * This is UX, not security. The FastAPI layer re-checks every request, so the
 * only thing this prevents is offering the user a button that would 403.
 */
export function PermissionGate({
  permission,
  anyOf,
  allOf,
  mode = "hide",
  fallback = null,
  children,
}: PermissionGateProps) {
  const { can, canAny, canAll } = usePermissions();

  const allowed =
    (permission ? can(permission) : true) &&
    (anyOf ? canAny(anyOf) : true) &&
    (allOf ? canAll(allOf) : true);

  if (allowed) return <>{children}</>;
  if (mode === "hide") return <>{fallback}</>;

  return (
    <div
      aria-disabled
      title="You don't have permission to do this"
      className="pointer-events-none opacity-50"
    >
      {children}
    </div>
  );
}

/**
 * Page-level guard.
 *
 * Renders `fallback` (usually a "no access" panel) rather than an empty screen
 * when the user lacks the permission a route needs.
 */
export function RequirePermission({
  permission,
  fallback,
  children,
}: {
  permission: string;
  fallback: React.ReactNode;
  children: React.ReactNode;
}) {
  const { can } = usePermissions();
  return <>{can(permission) ? children : fallback}</>;
}

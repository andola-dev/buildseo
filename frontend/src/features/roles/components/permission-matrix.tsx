"use client";

import { useMemo } from "react";
import { Check, X } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ACTION_LABELS, RESOURCE_LABELS } from "@/config/permissions";
import { humanizeEnum } from "@/config/labels";
import { cn } from "@/lib/utils/cn";
import type { Permission } from "@/types/api";

/** Group the flat catalogue by resource, preserving catalogue order. */
export function groupByResource(
  permissions: readonly Permission[],
): { resource: string; label: string; items: Permission[] }[] {
  const groups = new Map<string, Permission[]>();

  for (const permission of permissions) {
    const existing = groups.get(permission.resource);
    if (existing) existing.push(permission);
    else groups.set(permission.resource, [permission]);
  }

  return [...groups.entries()].map(([resource, items]) => ({
    resource,
    label: RESOURCE_LABELS[resource] ?? humanizeEnum(resource),
    items,
  }));
}

function actionLabel(permission: Permission): string {
  return ACTION_LABELS[permission.action] ?? humanizeEnum(permission.action);
}

/**
 * The permission matrix (spec §34).
 *
 * Read-only for seeded (system) roles: the backend refuses to change them, so
 * offering editable checkboxes would invite a rejection. Editable roles get
 * real checkboxes.
 */
export function PermissionMatrix({
  catalog,
  granted,
  onChange,
  readOnly = false,
}: {
  catalog: readonly Permission[];
  granted: readonly string[];
  onChange?: (codes: string[]) => void;
  readOnly?: boolean;
}) {
  const groups = useMemo(() => groupByResource(catalog), [catalog]);
  const grantedSet = useMemo(() => new Set(granted), [granted]);

  function toggle(code: string, checked: boolean) {
    if (!onChange) return;
    onChange(checked ? [...granted, code] : granted.filter((existing) => existing !== code));
  }

  return (
    <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
      {groups.map((group) => (
        <section key={group.resource}>
          <h3 className="mb-2 text-sm font-semibold">{group.label}</h3>
          <ul className="space-y-1.5">
            {group.items.map((permission) => {
              const isGranted = grantedSet.has(permission.code);

              if (readOnly) {
                return (
                  <li
                    key={permission.code}
                    className="flex items-center gap-2 text-sm"
                    title={permission.description ?? permission.code}
                  >
                    {isGranted ? (
                      <Check className="text-success size-4 shrink-0" aria-hidden />
                    ) : (
                      <X className="text-muted-foreground/50 size-4 shrink-0" aria-hidden />
                    )}
                    <span
                      className={cn(
                        isGranted ? "" : "text-muted-foreground",
                        "truncate",
                      )}
                    >
                      {actionLabel(permission)}
                    </span>
                    <span className="sr-only">
                      {isGranted ? "granted" : "not granted"}
                    </span>
                  </li>
                );
              }

              return (
                <li key={permission.code}>
                  <Label
                    htmlFor={`perm-${permission.code}`}
                    className="cursor-pointer items-start gap-2 font-normal"
                  >
                    <Checkbox
                      id={`perm-${permission.code}`}
                      checked={isGranted}
                      onCheckedChange={(checked) => toggle(permission.code, checked === true)}
                      className="mt-0.5"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm">{actionLabel(permission)}</span>
                      {permission.description ? (
                        <span className="text-muted-foreground block text-xs">
                          {permission.description}
                        </span>
                      ) : null}
                    </span>
                  </Label>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

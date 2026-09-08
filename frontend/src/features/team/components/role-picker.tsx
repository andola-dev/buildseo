"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ROLE_SLUG_LABELS } from "@/config/labels";
import { useRoles } from "@/features/roles/api/use-roles";

/**
 * Role assignment.
 *
 * Roles come from `/roles`, which returns the workspace's own copies — so a
 * custom role created for this workspace is offered without any client change
 * (spec §34).
 */
export function RolePicker({
  selected,
  onChange,
  error,
}: {
  selected: readonly string[];
  onChange: (slugs: string[]) => void;
  error?: string | undefined;
}) {
  const roles = useRoles();

  function toggle(slug: string, checked: boolean) {
    onChange(
      checked ? [...selected, slug] : selected.filter((existing) => existing !== slug),
    );
  }

  if (roles.isPending) {
    return (
      <div className="space-y-2" aria-hidden>
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (roles.error || (roles.data?.items.length ?? 0) === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No roles are available in this workspace.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {roles.data?.items.map((role) => (
          <Label
            key={role.id}
            htmlFor={`role-${role.id}`}
            className="hover:bg-accent/40 flex cursor-pointer items-start gap-2.5 rounded-md border p-2.5 font-normal"
          >
            <Checkbox
              id={`role-${role.id}`}
              checked={selected.includes(role.slug)}
              onCheckedChange={(checked) => toggle(role.slug, checked === true)}
              className="mt-0.5"
            />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">
                {ROLE_SLUG_LABELS[role.slug] ?? role.name}
              </span>
              {role.description ? (
                <span className="text-muted-foreground block text-xs">
                  {role.description}
                </span>
              ) : null}
            </span>
          </Label>
        ))}
      </div>

      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
}

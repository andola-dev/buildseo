"use client";

import { useState } from "react";
import { Copy, MoreHorizontal, Pencil, Plus, Shield, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { PermissionGate } from "@/components/shared/permission-gate";
import { PermissionMatrix } from "@/features/roles/components/permission-matrix";
import {
  RoleDialog,
  type RoleDialogMode,
} from "@/features/roles/components/role-dialog";
import {
  useDeleteRole,
  usePermissionCatalog,
  useRoles,
} from "@/features/roles/api/use-roles";
import { ROLE_SLUG_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { errorMessage } from "@/lib/api/errors";
import { formatNumber } from "@/lib/utils/format";
import type { Role } from "@/types/api";

/**
 * Roles and their permissions (spec §34).
 *
 * The matrix is rendered from the backend's permission catalogue, so nothing
 * about authorization is hardcoded here — the frontend only shows what the
 * backend reports and enforces.
 */
export function RolesView() {
  const roles = useRoles();
  const catalog = usePermissionCatalog();
  const deleteRole = useDeleteRole();

  const [dialog, setDialog] = useState<RoleDialogMode | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Role | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (roles.isPending) {
    return (
      <div className="space-y-3" aria-hidden>
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index}>
            <CardHeader>
              <Skeleton className="h-4 w-40" />
            </CardHeader>
            <CardContent className="pt-0">
              <Skeleton className="h-3 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (roles.error) {
    return (
      <ErrorState error={roles.error} resource="roles" onRetry={() => void roles.refetch()} />
    );
  }

  const items = roles.data?.items ?? [];

  if (items.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={Shield}
          title="No roles yet"
          description="Roles group the permissions a member has in this workspace."
          action={
            <PermissionGate permission={PERM.ROLE_CREATE}>
              <Button size="sm" onClick={() => setDialog({ kind: "create" })}>
                <Plus className="size-4" aria-hidden />
                Create role
              </Button>
            </PermissionGate>
          }
        />
      </Card>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-end">
        <PermissionGate permission={PERM.ROLE_CREATE}>
          <Button size="sm" onClick={() => setDialog({ kind: "create" })}>
            <Plus className="size-4" aria-hidden />
            Create role
          </Button>
        </PermissionGate>
      </div>

      <div className="space-y-3">
        {items.map((role) => {
          const isOpen = expanded === role.id;
          const grantedCount = role.permissions?.length ?? 0;

          return (
            <Card key={role.id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      {ROLE_SLUG_LABELS[role.slug] ?? role.name}
                      {role.is_system ? <Badge variant="muted">System</Badge> : null}
                    </CardTitle>
                    <p className="text-muted-foreground mt-1 text-sm">
                      {role.description ??
                        `${formatNumber(grantedCount)} permission${grantedCount === 1 ? "" : "s"} granted`}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setExpanded(isOpen ? null : role.id)}
                      aria-expanded={isOpen}
                    >
                      {isOpen ? "Hide permissions" : "View permissions"}
                    </Button>

                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Actions for ${role.name}`}
                        >
                          <MoreHorizontal className="size-4" aria-hidden />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-44">
                        <PermissionGate permission={PERM.ROLE_UPDATE}>
                          <DropdownMenuItem
                            onSelect={() => setDialog({ kind: "edit", role })}
                            disabled={role.is_system}
                          >
                            <Pencil className="size-4" aria-hidden />
                            Edit role
                          </DropdownMenuItem>
                        </PermissionGate>

                        <PermissionGate permission={PERM.ROLE_CREATE}>
                          <DropdownMenuItem
                            onSelect={() => setDialog({ kind: "clone", role })}
                          >
                            <Copy className="size-4" aria-hidden />
                            Clone role
                          </DropdownMenuItem>
                        </PermissionGate>

                        <PermissionGate permission={PERM.ROLE_DELETE}>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            variant="destructive"
                            onSelect={() => setPendingDelete(role)}
                            disabled={role.is_system}
                          >
                            <Trash2 className="size-4" aria-hidden />
                            Delete role
                          </DropdownMenuItem>
                        </PermissionGate>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </CardHeader>

              {isOpen ? (
                <CardContent className="pt-0">
                  {catalog.isPending ? (
                    <p className="text-muted-foreground text-sm">
                      Loading permission catalogue…
                    </p>
                  ) : catalog.error || !catalog.data ? (
                    <ErrorState
                      error={catalog.error}
                      resource="the permission catalogue"
                      onRetry={() => void catalog.refetch()}
                    />
                  ) : (
                    <PermissionMatrix
                      catalog={catalog.data}
                      granted={role.permissions ?? []}
                      readOnly
                    />
                  )}
                </CardContent>
              ) : null}
            </Card>
          );
        })}
      </div>

      <RoleDialog mode={dialog} onOpenChange={(open) => !open && setDialog(null)} />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this role?"
        description={
          <>
            <strong>{pendingDelete?.name}</strong> will be removed. Members who hold only this
            role will lose their permissions in this workspace until another role is assigned.
          </>
        }
        confirmLabel="Delete role"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            await deleteRole.mutateAsync(pendingDelete.id);
            toast.success("Role deleted");
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't delete role", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}

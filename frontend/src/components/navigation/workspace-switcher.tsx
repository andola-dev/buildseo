"use client";

import { useState } from "react";
import { Building2, Check, ChevronsUpDown, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CreateWorkspaceDialog } from "@/features/settings/components/create-workspace-dialog";
import { PermissionGate } from "@/components/shared/permission-gate";
import { errorMessage } from "@/lib/api/errors";
import { useTenant } from "@/lib/tenant/use-tenant";
import { cn } from "@/lib/utils/cn";

/**
 * Workspace selector (spec §9).
 *
 * Selecting a workspace mints a new workspace-scoped access token, removes
 * every tenant-scoped cache entry and refetches permissions — all handled by
 * `switchTenant`. This component only presents the choice.
 */
export function WorkspaceSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { tenants, activeTenant, activeTenantId, switchTenant, switchingTenant } =
    useTenant();
  const [createOpen, setCreateOpen] = useState(false);

  async function handleSelect(tenantId: string) {
    if (tenantId === activeTenantId) return;
    try {
      await switchTenant(tenantId);
    } catch (error) {
      toast.error("Couldn't switch workspace", { description: errorMessage(error) });
    }
  }

  const label = activeTenant?.tenant_name ?? "Select workspace";

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className={cn(
              "h-auto w-full justify-start gap-2 px-2 py-2 text-left",
              "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              collapsed && "justify-center px-0",
            )}
            aria-label={`Current workspace: ${label}. Change workspace`}
          >
            <span className="bg-sidebar-primary text-sidebar-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-md">
              {switchingTenant ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <Building2 className="size-3.5" aria-hidden />
              )}
            </span>

            {collapsed ? null : (
              <>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{label}</span>
                  <span className="text-muted-foreground block truncate text-xs">
                    {activeTenant?.is_owner ? "Owner" : (activeTenant?.roles?.[0] ?? "Member")}
                  </span>
                </span>
                <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" aria-hidden />
              </>
            )}
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="start" className="w-60">
          <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
          <DropdownMenuSeparator />

          {tenants.length === 0 ? (
            <div className="text-muted-foreground px-2 py-3 text-sm">
              You don&apos;t belong to any workspace yet.
            </div>
          ) : (
            tenants.map((tenant) => (
              <DropdownMenuItem
                key={tenant.tenant_id}
                onSelect={() => void handleSelect(tenant.tenant_id)}
                disabled={switchingTenant}
              >
                <Check
                  className={cn(
                    "size-4",
                    tenant.tenant_id !== activeTenantId && "invisible",
                  )}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate">{tenant.tenant_name}</span>
                {tenant.status !== "ACTIVE" ? (
                  <span className="text-muted-foreground text-xs">{tenant.status}</span>
                ) : null}
              </DropdownMenuItem>
            ))
          )}

          <PermissionGate>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setCreateOpen(true)}>
              <Plus className="size-4" aria-hidden />
              Create workspace
            </DropdownMenuItem>
          </PermissionGate>
        </DropdownMenuContent>
      </DropdownMenu>

      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Field, fieldAria } from "@/components/forms/field";
import { DefinitionList } from "@/components/shared/definition-list";
import { PermissionGate } from "@/components/shared/permission-gate";
import { StatusBadge } from "@/components/shared/status-badge";
import { TENANT_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { useUpdateWorkspace } from "@/features/settings/api/use-workspaces";
import { tenantsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenant, useTenantId } from "@/lib/tenant/use-tenant";
import { useQuery } from "@tanstack/react-query";
import { workspaceSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { formatDate } from "@/lib/utils/format";

/** Workspace profile and the user's workspace list (spec §31). */
export function WorkspaceSettings() {
  const tenantId = useTenantId();
  const { tenants, activeTenantId, switchTenant } = useTenant();

  const workspace = useQuery({
    queryKey: queryKeys.workspace.detail(tenantId),
    queryFn: () => tenantsApi.getTenant(tenantId!),
    enabled: Boolean(tenantId),
  });

  const updateWorkspace = useUpdateWorkspace(tenantId);
  const { fieldError, formError, validate, applyServerError } = useFormErrors();
  const [name, setName] = useState("");

  useEffect(() => {
    if (workspace.data) setName(workspace.data.name);
  }, [workspace.data]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(workspaceSchema, { name, slug: "" });
    if (!values) return;

    try {
      await updateWorkspace.mutateAsync({ name: values.name });
      toast.success("Workspace updated");
    } catch (error) {
      applyServerError(error);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Workspace</h2>
        <p className="text-muted-foreground text-sm">
          Every client website, campaign, publisher and submission belongs to one workspace.
        </p>
      </div>

      {workspace.isPending ? (
        <DetailSkeleton />
      ) : workspace.error || !workspace.data ? (
        <ErrorState
          error={workspace.error}
          resource="this workspace"
          onRetry={() => void workspace.refetch()}
        />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5 pt-0">
              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {formError ? (
                  <Alert variant="destructive">
                    <AlertDescription>{formError}</AlertDescription>
                  </Alert>
                ) : null}

                <Field
                  id="workspace-name-setting"
                  label="Workspace name"
                  required
                  error={fieldError("name")}
                >
                  <Input
                    {...fieldAria("workspace-name-setting", { error: fieldError("name") })}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </Field>

                <PermissionGate permission={PERM.TENANT_UPDATE} mode="disable">
                  <Button type="submit" size="sm" loading={updateWorkspace.isPending}>
                    Save changes
                  </Button>
                </PermissionGate>
              </form>

              <DefinitionList
                items={[
                  { label: "Slug", value: workspace.data.slug },
                  {
                    label: "Status",
                    value: (
                      <StatusBadge
                        status={workspace.data.status}
                        labels={TENANT_STATUS_LABELS}
                      />
                    ),
                  },
                  { label: "Created", value: formatDate(workspace.data.created_at) },
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Your workspaces</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <ul className="divide-y">
                {tenants.map((tenant) => (
                  <li key={tenant.tenant_id} className="flex items-center gap-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {tenant.tenant_name}
                      </div>
                      <div className="text-muted-foreground truncate text-xs">
                        {tenant.is_owner ? "Owner" : (tenant.roles ?? []).join(", ") || "Member"}
                      </div>
                    </div>

                    {tenant.tenant_id === activeTenantId ? (
                      <span className="text-muted-foreground text-xs">Active</span>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void switchTenant(tenant.tenant_id)}
                      >
                        Switch
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

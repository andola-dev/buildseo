"use client";

import { useState } from "react";
import { KeyRound, MoreHorizontal, Plus, RefreshCw, Trash2 } from "lucide-react";
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
import { StatusBadge } from "@/components/shared/status-badge";
import {
  CredentialDialog,
  type ProviderOption,
} from "@/features/credentials/components/credential-dialog";
import {
  useCredentials,
  useDeleteCredential,
  useVerifyCredential,
} from "@/features/credentials/api/use-credentials";
import { CREDENTIAL_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils/format";
import type { Credential, CredentialProviderType } from "@/types/api";

/**
 * Configured provider credentials (spec §32).
 *
 * Each row shows only what the API returns: provider, label, status and
 * `masked_key`. There is no code path that could display a full key, because
 * the read model does not contain one.
 */
export function CredentialList({
  providerType,
  providers,
  title,
  description,
  emptyDescription,
}: {
  providerType: CredentialProviderType;
  providers: readonly ProviderOption[];
  title: string;
  description: string;
  emptyDescription: string;
}) {
  const credentials = useCredentials({ provider_type: providerType });
  const verifyCredential = useVerifyCredential();
  const deleteCredential = useDeleteCredential();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [rotating, setRotating] = useState<Credential | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Credential | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const configured = credentials.data?.items ?? [];
  const configuredProviders = new Set(configured.map((entry) => entry.provider));

  async function handleVerify(credential: Credential) {
    setVerifyingId(credential.id);
    try {
      const result = await verifyCredential.mutateAsync(credential.id);
      if (result.verified) {
        toast.success("Connection verified", {
          description: `${credential.label} works.`,
        });
      } else {
        toast.error("Verification failed", {
          description: result.error_code
            ? `The provider rejected the key (${result.error_code}).`
            : "The provider rejected the key.",
        });
      }
    } catch (error) {
      toast.error("Couldn't test the connection", { description: errorMessage(error) });
    } finally {
      setVerifyingId(null);
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle>{title}</CardTitle>
              <p className="text-muted-foreground mt-1 text-sm">{description}</p>
            </div>
            <PermissionGate permission={PERM.CREDENTIAL_CREATE}>
              <Button
                size="sm"
                onClick={() => {
                  setRotating(null);
                  setDialogOpen(true);
                }}
              >
                <Plus className="size-4" aria-hidden />
                Add provider
              </Button>
            </PermissionGate>
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          {credentials.isPending ? (
            <div className="space-y-2" aria-hidden>
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-14 w-full" />
              ))}
            </div>
          ) : credentials.error ? (
            <ErrorState
              error={credentials.error}
              resource="your provider credentials"
              onRetry={() => void credentials.refetch()}
            />
          ) : (
            <ul className="divide-y">
              {/* Configured providers first, then the rest as "Not configured",
                  so the whole supported set is visible at a glance (spec §32). */}
              {configured.map((credential) => (
                <li
                  key={credential.id}
                  className="flex flex-wrap items-center gap-3 py-3 first:pt-0"
                >
                  <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-md">
                    <KeyRound className="size-4" aria-hidden />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {credential.label}
                      </span>
                      <StatusBadge
                        status={credential.status}
                        labels={CREDENTIAL_STATUS_LABELS}
                      />
                    </div>
                    <div className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
                      <span>{credential.provider}</span>
                      <span className="tabular">Key: {credential.masked_key}</span>
                      {credential.last_verified_at ? (
                        <span>Verified {formatDateTime(credential.last_verified_at)}</span>
                      ) : null}
                    </div>
                  </div>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Actions for ${credential.label}`}
                      >
                        <MoreHorizontal className="size-4" aria-hidden />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                      <PermissionGate permission={PERM.CREDENTIAL_UPDATE}>
                        <DropdownMenuItem
                          disabled={verifyingId === credential.id}
                          onSelect={(event) => {
                            event.preventDefault();
                            void handleVerify(credential);
                          }}
                        >
                          <RefreshCw className="size-4" aria-hidden />
                          {verifyingId === credential.id ? "Testing…" : "Test connection"}
                        </DropdownMenuItem>

                        <DropdownMenuItem
                          onSelect={() => {
                            setRotating(credential);
                            setDialogOpen(true);
                          }}
                        >
                          Replace key
                        </DropdownMenuItem>
                      </PermissionGate>

                      <PermissionGate permission={PERM.CREDENTIAL_DELETE}>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          variant="destructive"
                          onSelect={() => setPendingDelete(credential)}
                        >
                          <Trash2 className="size-4" aria-hidden />
                          Remove
                        </DropdownMenuItem>
                      </PermissionGate>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </li>
              ))}

              {providers
                .filter((provider) => !configuredProviders.has(provider.value))
                .map((provider) => (
                  <li
                    key={provider.value}
                    className="flex items-center gap-3 py-3 first:pt-0"
                  >
                    <span className="bg-muted/50 text-muted-foreground/60 flex size-8 shrink-0 items-center justify-center rounded-md">
                      <KeyRound className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <span className="text-sm">{provider.label}</span>
                    </div>
                    <Badge variant="muted">Not configured</Badge>
                    <PermissionGate permission={PERM.CREDENTIAL_CREATE}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setRotating(null);
                          setDialogOpen(true);
                        }}
                      >
                        Add
                      </Button>
                    </PermissionGate>
                  </li>
                ))}

              {configured.length === 0 && providers.length === 0 ? (
                <EmptyState
                  icon={KeyRound}
                  title="No providers configured"
                  description={emptyDescription}
                />
              ) : null}
            </ul>
          )}
        </CardContent>
      </Card>

      <CredentialDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setRotating(null);
        }}
        providerType={providerType}
        providers={providers}
        credential={rotating}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this credential?"
        description={
          <>
            <strong>{pendingDelete?.label}</strong> will be destroyed on the server and can&apos;t
            be recovered. Anything that depends on it — content generation, discovery — will
            stop working until another key is configured.
          </>
        }
        confirmLabel="Remove credential"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            // The backend destroys the encrypted key; removing it from the
            // client alone would leave it live on the server (spec §67).
            await deleteCredential.mutateAsync(pendingDelete.id);
            toast.success("Credential removed", {
              description: "The key has been destroyed on the server.",
            });
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't remove credential", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}

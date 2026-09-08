"use client";

import { useState } from "react";
import { Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Field } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { PermissionGate } from "@/components/shared/permission-gate";
import { CredentialList } from "@/features/credentials/components/credential-list";
import {
  useAiConfigs,
  useCredentials,
  useDeleteAiConfig,
  useUpsertAiConfig,
} from "@/features/credentials/api/use-credentials";
import { AI_PROVIDERS, AI_PURPOSES } from "@/config/enums";
import { AI_PROVIDER_LABELS, AI_PURPOSE_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { errorMessage } from "@/lib/api/errors";
import type { AiConfig, AiProvider, AiPurpose } from "@/types/api";

const AI_PROVIDER_OPTIONS = AI_PROVIDERS.map((provider) => ({
  value: provider,
  label: AI_PROVIDER_LABELS[provider],
}));

/**
 * Bind a purpose to a provider, model and stored key.
 *
 * The credential is referenced by id — the key itself is never part of this
 * form, which is what keeps the two concerns separate (spec §32).
 */
function AiConfigDialog({
  open,
  onOpenChange,
  config,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: AiConfig | null;
}) {
  const credentials = useCredentials({ provider_type: "AI" });
  const upsert = useUpsertAiConfig();

  const [purpose, setPurpose] = useState<AiPurpose>(
    (config?.purpose as AiPurpose | undefined) ?? "content_generation",
  );
  const [provider, setProvider] = useState<AiProvider>(
    (config?.provider as AiProvider | undefined) ?? "openai",
  );
  const [model, setModel] = useState(config?.model ?? "");
  const [credentialId, setCredentialId] = useState(config?.credential_id ?? "");
  const [error, setError] = useState<string | undefined>();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!model.trim()) {
      setError("Enter the model name your provider expects.");
      return;
    }
    setError(undefined);

    try {
      await upsert.mutateAsync({
        purpose,
        provider,
        model: model.trim(),
        credential_id: credentialId || null,
        is_default: true,
      });
      toast.success("AI configuration saved");
      onOpenChange(false);
    } catch (caught) {
      toast.error("Couldn't save configuration", { description: errorMessage(caught) });
      setError(errorMessage(caught));
    }
  }

  const available = (credentials.data?.items ?? []).filter(
    (credential) => credential.provider === provider,
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={config ? "Edit AI configuration" : "Configure AI"}
      description="Choose which provider and model handle each task. Requests are made by the backend using your stored key."
      submitLabel="Save configuration"
      submitting={upsert.isPending}
      onSubmit={handleSubmit}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Field id="ai-purpose" label="Purpose" required>
        <Select
          value={purpose}
          onValueChange={(value) => setPurpose(value as AiPurpose)}
          disabled={Boolean(config)}
        >
          <SelectTrigger id="ai-purpose" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AI_PURPOSES.map((option) => (
              <SelectItem key={option} value={option}>
                {AI_PURPOSE_LABELS[option]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field id="ai-provider" label="Provider" required>
        <Select value={provider} onValueChange={(value) => setProvider(value as AiProvider)}>
          <SelectTrigger id="ai-provider" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AI_PROVIDERS.map((option) => (
              <SelectItem key={option} value={option}>
                {AI_PROVIDER_LABELS[option]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field
        id="ai-model"
        label="Model"
        required
        hint="The model identifier your provider expects."
      >
        <Input
          id="ai-model"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="gpt-4o-mini"
        />
      </Field>

      <Field
        id="ai-credential"
        label="Credential"
        hint={
          available.length === 0
            ? "No key is configured for this provider yet. Add one below first."
            : "Which stored key to use."
        }
      >
        <Select value={credentialId} onValueChange={setCredentialId}>
          <SelectTrigger id="ai-credential" className="w-full">
            <SelectValue placeholder="Workspace default" />
          </SelectTrigger>
          <SelectContent>
            {available.map((credential) => (
              <SelectItem key={credential.id} value={credential.id}>
                {credential.label} · {credential.masked_key}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
    </FormDialog>
  );
}

/** AI provider settings: stored keys plus per-purpose configuration (spec §32). */
export function AiSettings() {
  const configs = useAiConfigs();
  const deleteConfig = useDeleteAiConfig();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AiConfig | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AiConfig | null>(null);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">AI Providers</h2>
        <p className="text-muted-foreground text-sm">
          Bring your own key. Keys are encrypted at rest and used only by the backend —
          they are never sent to or stored in your browser.
        </p>
      </div>

      <CredentialList
        providerType="AI"
        providers={AI_PROVIDER_OPTIONS}
        title="Provider keys"
        description="Add a key for each AI provider you want this workspace to use."
        emptyDescription="Add a provider key to enable AI listing-content generation."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle>Task configuration</CardTitle>
              <p className="text-muted-foreground mt-1 text-sm">
                Which provider and model handle each task.
              </p>
            </div>
            <PermissionGate permission={PERM.CREDENTIAL_UPDATE}>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditing(null);
                  setDialogOpen(true);
                }}
              >
                Configure
              </Button>
            </PermissionGate>
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          {configs.isPending ? (
            <div className="space-y-2" aria-hidden>
              {Array.from({ length: 2 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : configs.error ? (
            <ErrorState
              error={configs.error}
              resource="AI configuration"
              onRetry={() => void configs.refetch()}
            />
          ) : (configs.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon={Sparkles}
              title="No AI tasks configured"
              description="Configure at least content generation so listing copy can be drafted for you."
              action={
                <PermissionGate permission={PERM.CREDENTIAL_UPDATE}>
                  <Button
                    size="sm"
                    onClick={() => {
                      setEditing(null);
                      setDialogOpen(true);
                    }}
                  >
                    Configure AI
                  </Button>
                </PermissionGate>
              }
            />
          ) : (
            <ul className="divide-y">
              {configs.data?.map((config) => (
                <li key={config.id} className="flex items-center gap-3 py-3 first:pt-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">
                        {AI_PURPOSE_LABELS[config.purpose as AiPurpose] ?? config.purpose}
                      </span>
                      {config.is_default ? <Badge variant="info">Default</Badge> : null}
                    </div>
                    <div className="text-muted-foreground text-xs">
                      {AI_PROVIDER_LABELS[config.provider as AiProvider] ?? config.provider} ·{" "}
                      {config.model}
                    </div>
                  </div>

                  <PermissionGate permission={PERM.CREDENTIAL_UPDATE}>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditing(config);
                        setDialogOpen(true);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setPendingDelete(config)}
                      aria-label="Remove configuration"
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </PermissionGate>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Alert variant="info">
        <Sparkles aria-hidden />
        <AlertTitle>Generation runs on the server</AlertTitle>
        <AlertDescription>
          The browser asks the backend to generate content; the backend calls the provider
          with your stored key. No provider credential is ever present in frontend code.
        </AlertDescription>
      </Alert>

      {dialogOpen ? (
        <AiConfigDialog
          open={dialogOpen}
          onOpenChange={(open) => {
            setDialogOpen(open);
            if (!open) setEditing(null);
          }}
          config={editing}
        />
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this AI configuration?"
        description={
          <>
            {AI_PURPOSE_LABELS[pendingDelete?.purpose as AiPurpose] ?? pendingDelete?.purpose}{" "}
            will no longer have a provider assigned, and requests for it will fail until you
            configure one again. The stored key is not deleted.
          </>
        }
        confirmLabel="Remove configuration"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            await deleteConfig.mutateAsync(pendingDelete.id);
            toast.success("Configuration removed");
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't remove configuration", {
              description: errorMessage(error),
            });
            throw error;
          }
        }}
      />
    </div>
  );
}

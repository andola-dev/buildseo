"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field, fieldAria } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import {
  useCreateCredential,
  useUpdateCredential,
} from "@/features/credentials/api/use-credentials";
import { AI_PROVIDER_LABELS } from "@/config/labels";
import { credentialSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import type { Credential, CredentialProviderType } from "@/types/api";

export interface ProviderOption {
  value: string;
  label: string;
}

/**
 * Add or rotate a provider credential (spec §32).
 *
 * Handling of the secret is the point of this component:
 *
 * - it lives only in this component's local state, never in a store, the query
 *   cache, `localStorage` or the URL;
 * - it is cleared as soon as the request resolves, success or failure, so it
 *   isn't left in a mounted component's state;
 * - it is never logged — including in an error path, where `applyServerError`
 *   only ever sees the response;
 * - the read model has no key field at all, so nothing can read it back.
 */
export function CredentialDialog({
  open,
  onOpenChange,
  providerType,
  providers,
  /** Present when rotating an existing credential rather than adding one. */
  credential,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerType: CredentialProviderType;
  providers: readonly ProviderOption[];
  credential?: Credential | null;
}) {
  const [provider, setProvider] = useState("");
  const [label, setLabel] = useState("");
  const [secret, setSecret] = useState("");
  const [verify, setVerify] = useState(true);

  const { fieldError, formError, validate, applyServerError, clear } = useFormErrors();
  const createCredential = useCreateCredential();
  const updateCredential = useUpdateCredential();

  const rotating = Boolean(credential);

  useEffect(() => {
    clear();
    setSecret("");
    setVerify(true);

    if (credential) {
      setProvider(credential.provider);
      setLabel(credential.label);
    } else {
      setProvider(providers[0]?.value ?? "");
      setLabel("");
    }
    // `clear` is stable; re-running on providers identity would clobber typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credential, open]);

  /** Discard the secret from component state. */
  function wipeSecret() {
    setSecret("");
  }

  function reset() {
    wipeSecret();
    setLabel("");
    clear();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(credentialSchema, { provider, label, secret, verify });
    if (!values) return;

    try {
      if (credential) {
        await updateCredential.mutateAsync({
          credentialId: credential.id,
          payload: {
            label: values.label,
            secret: values.secret,
            verify: values.verify,
          },
        });
        toast.success("Key replaced", {
          description: "The previous key has been destroyed on the server.",
        });
      } else {
        await createCredential.mutateAsync({
          provider: values.provider,
          provider_type: providerType,
          label: values.label,
          secret: values.secret,
          verify: values.verify,
        });
        toast.success("Credential stored", {
          description: "The key is encrypted at rest and never returned to the browser.",
        });
      }

      reset();
      onOpenChange(false);
    } catch (error) {
      applyServerError(error);
    } finally {
      // Clear the plaintext key whatever happened, so a failed submit doesn't
      // leave it sitting in state while the dialog stays open.
      wipeSecret();
    }
  }

  const submitting = createCredential.isPending || updateCredential.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
      title={rotating ? "Replace key" : "Add provider"}
      description={
        rotating
          ? "Paste a new key. The current one is destroyed once the new key is stored."
          : "Your key is sent once, encrypted at rest, and used only by the backend."
      }
      submitLabel={rotating ? "Replace key" : "Add provider"}
      submitting={submitting}
      onSubmit={handleSubmit}
    >
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Field id="credential-provider" label="Provider" required error={fieldError("provider")}>
        <Select value={provider} onValueChange={setProvider} disabled={rotating}>
          <SelectTrigger id="credential-provider" className="w-full">
            <SelectValue placeholder="Choose a provider" />
          </SelectTrigger>
          <SelectContent>
            {providers.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {AI_PROVIDER_LABELS[option.value as keyof typeof AI_PROVIDER_LABELS] ??
                  option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field
        id="credential-label"
        label="Label"
        required
        error={fieldError("label")}
        hint="How you'll recognise this key, e.g. “Production OpenAI”."
      >
        <Input
          {...fieldAria("credential-label", { error: fieldError("label") })}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Production key"
        />
      </Field>

      <Field id="credential-secret" label="API key" required error={fieldError("secret")}>
        <Input
          {...fieldAria("credential-secret", { error: fieldError("secret") })}
          type="password"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          // The browser must not offer to remember a provider secret.
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          data-1p-ignore
          data-lpignore="true"
          placeholder="sk-…"
        />
      </Field>

      <div className="flex items-start gap-2">
        <Checkbox
          id="credential-verify"
          checked={verify}
          onCheckedChange={(checked) => setVerify(checked === true)}
        />
        <Label htmlFor="credential-verify" className="font-normal">
          Test the key with the provider before saving
        </Label>
      </div>

      <Alert variant="info">
        <ShieldCheck aria-hidden />
        <AlertTitle>How your key is handled</AlertTitle>
        <AlertDescription>
          It is sent once over TLS, encrypted at rest by the backend, and used only
          server-side. It is never stored in your browser and never returned by the API —
          you&apos;ll only ever see the last few characters.
        </AlertDescription>
      </Alert>
    </FormDialog>
  );
}

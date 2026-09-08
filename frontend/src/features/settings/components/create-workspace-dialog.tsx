"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Field, fieldAria } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { useCreateWorkspace } from "@/features/settings/api/use-workspaces";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { workspaceSchema } from "@/lib/validation/schemas";

/**
 * Create a workspace (spec §9).
 *
 * The slug is optional: the backend derives one from the name when it is
 * omitted, and duplicating that logic here would risk disagreeing with it.
 */
export function CreateWorkspaceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const { fieldError, formError, validate, applyServerError, clear } = useFormErrors();
  const createWorkspace = useCreateWorkspace();

  function reset() {
    setName("");
    setSlug("");
    clear();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(workspaceSchema, { name, slug });
    if (!values) return;

    try {
      const tenant = await createWorkspace.mutateAsync({
        name: values.name,
        ...(values.slug ? { slug: values.slug } : {}),
      });

      toast.success("Workspace created", {
        description: `${tenant.name} is ready. Switch to it from the workspace menu.`,
      });
      reset();
      onOpenChange(false);
    } catch (error) {
      applyServerError(error);
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
      title="Create workspace"
      description="A workspace keeps its client websites, campaigns and team separate from every other workspace."
      submitLabel="Create workspace"
      submitting={createWorkspace.isPending}
      onSubmit={handleSubmit}
    >
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Field id="workspace-name" label="Name" required error={fieldError("name")}>
        <Input
          {...fieldAria("workspace-name", { error: fieldError("name") })}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Marketing"
          autoFocus
        />
      </Field>

      <Field
        id="workspace-slug"
        label="Slug"
        error={fieldError("slug")}
        hint="Optional. Leave blank and one will be generated from the name."
      >
        <Input
          {...fieldAria("workspace-slug", { error: fieldError("slug") })}
          value={slug}
          onChange={(event) => setSlug(event.target.value.toLowerCase())}
          placeholder="acme-marketing"
        />
      </Field>
    </FormDialog>
  );
}

"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, fieldAria } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { PermissionMatrix } from "@/features/roles/components/permission-matrix";
import {
  useCreateRole,
  usePermissionCatalog,
  useUpdateRole,
} from "@/features/roles/api/use-roles";
import { roleSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import type { Role } from "@/types/api";

export type RoleDialogMode =
  | { kind: "create" }
  | { kind: "edit"; role: Role }
  | { kind: "clone"; role: Role };

/**
 * Create, edit or clone a role (spec §34).
 *
 * Cloning is a create with the source role's permissions pre-selected — the
 * backend has no clone endpoint, and copying client-side against the catalogue
 * it just returned gives the same result without inventing an API.
 */
export function RoleDialog({
  mode,
  onOpenChange,
}: {
  mode: RoleDialogMode | null;
  onOpenChange: (open: boolean) => void;
}) {
  const catalog = usePermissionCatalog();
  const createRole = useCreateRole();
  const updateRole = useUpdateRole();
  const { fieldError, formError, validate, applyServerError, clear } = useFormErrors();

  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissions, setPermissions] = useState<string[]>([]);

  useEffect(() => {
    clear();

    if (!mode) {
      setSlug("");
      setName("");
      setDescription("");
      setPermissions([]);
      return;
    }

    if (mode.kind === "create") {
      setSlug("");
      setName("");
      setDescription("");
      setPermissions([]);
      return;
    }

    const source = mode.role;
    setPermissions([...(source.permissions ?? [])]);
    setDescription(source.description ?? "");

    if (mode.kind === "edit") {
      setSlug(source.slug);
      setName(source.name);
    } else {
      // A clone needs its own identity, so the slug and name start fresh
      // rather than colliding with the source role.
      setSlug(`${source.slug}-copy`);
      setName(`${source.name} (copy)`);
    }
    // `clear` is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const editing = mode?.kind === "edit";
  const submitting = createRole.isPending || updateRole.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(roleSchema, { slug, name, description, permissions });
    if (!values) return;

    try {
      if (editing && mode.kind === "edit") {
        await updateRole.mutateAsync({
          roleId: mode.role.id,
          payload: {
            name: values.name,
            description: values.description || null,
            permissions: values.permissions,
          },
        });
        toast.success("Role updated");
      } else {
        await createRole.mutateAsync({
          slug: values.slug,
          name: values.name,
          description: values.description || null,
          permissions: values.permissions,
        });
        toast.success("Role created");
      }
      onOpenChange(false);
    } catch (error) {
      applyServerError(error);
    }
  }

  return (
    <FormDialog
      open={mode !== null}
      onOpenChange={onOpenChange}
      title={
        editing ? "Edit role" : mode?.kind === "clone" ? "Clone role" : "Create role"
      }
      description="Choose exactly what this role can do. The backend enforces these permissions on every request."
      submitLabel={editing ? "Save role" : "Create role"}
      submitting={submitting}
      onSubmit={handleSubmit}
    >
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="role-name" label="Name" required error={fieldError("name")}>
          <Input
            {...fieldAria("role-name", { error: fieldError("name") })}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Outreach Specialist"
          />
        </Field>

        <Field
          id="role-slug"
          label="Slug"
          required
          error={fieldError("slug")}
          hint={editing ? "The slug can't be changed." : "Lowercase, hyphens or underscores."}
        >
          <Input
            {...fieldAria("role-slug", { error: fieldError("slug") })}
            value={slug}
            onChange={(event) => setSlug(event.target.value.toLowerCase())}
            placeholder="outreach_specialist"
            disabled={editing}
          />
        </Field>
      </div>

      <Field id="role-description" label="Description" error={fieldError("description")}>
        <Textarea
          {...fieldAria("role-description", { error: fieldError("description") })}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
        />
      </Field>

      <Field
        id="role-permissions"
        label="Permissions"
        required
        error={fieldError("permissions")}
      >
        {catalog.isPending ? (
          <p className="text-muted-foreground text-sm">Loading permission catalogue…</p>
        ) : catalog.error || !catalog.data ? (
          <p className="text-destructive text-sm">
            The permission catalogue couldn&apos;t be loaded, so permissions can&apos;t be
            edited right now.
          </p>
        ) : (
          <div className="max-h-80 overflow-y-auto rounded-md border p-3">
            <PermissionMatrix
              catalog={catalog.data}
              granted={permissions}
              onChange={setPermissions}
            />
          </div>
        )}
      </Field>
    </FormDialog>
  );
}

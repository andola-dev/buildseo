"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Field, fieldAria } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { RolePicker } from "@/features/team/components/role-picker";
import { useAddMember } from "@/features/team/api/use-team";
import { memberInviteSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";

/**
 * Add a member to the workspace (spec §33).
 *
 * The backend matches the address to an existing account and creates the
 * membership. No email is sent — the product sends no email of any kind
 * (spec §72) — so the copy tells the admin to pass the news along themselves.
 */
export function InviteMemberDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [roleSlugs, setRoleSlugs] = useState<string[]>([]);
  const { fieldError, formError, validate, applyServerError, clear } = useFormErrors();
  const addMember = useAddMember();

  function reset() {
    setEmail("");
    setRoleSlugs([]);
    clear();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(memberInviteSchema, { email, role_slugs: roleSlugs });
    if (!values) return;

    try {
      await addMember.mutateAsync({
        email: values.email,
        role_slugs: values.role_slugs,
        status: "ACTIVE",
      });
      toast.success("Member added", {
        description: "Let them know they now have access to this workspace.",
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
      title="Add workspace member"
      description="The person must already have an account. Adding them grants access immediately."
      submitLabel="Add member"
      submitting={addMember.isPending}
      onSubmit={handleSubmit}
    >
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Field id="member-email" label="Email address" required error={fieldError("email")}>
        <Input
          {...fieldAria("member-email", { error: fieldError("email") })}
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="teammate@company.com"
          autoFocus
        />
      </Field>

      <Field id="member-roles" label="Roles" required error={fieldError("role_slugs")}>
        <RolePicker
          selected={roleSlugs}
          onChange={setRoleSlugs}
          error={fieldError("role_slugs")}
        />
      </Field>
    </FormDialog>
  );
}

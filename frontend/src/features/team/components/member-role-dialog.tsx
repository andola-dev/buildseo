"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { RolePicker } from "@/features/team/components/role-picker";
import { useUpdateMember } from "@/features/team/api/use-team";
import { errorMessage } from "@/lib/api/errors";
import { userDisplayName } from "@/lib/utils/format";
import type { Membership } from "@/types/api";

/** Change a member's roles (spec §33). */
export function MemberRoleDialog({
  member,
  onOpenChange,
}: {
  member: Membership | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [roleSlugs, setRoleSlugs] = useState<string[]>([]);
  const [error, setError] = useState<string | undefined>();
  const updateMember = useUpdateMember();

  // Reset to the member's current roles whenever the dialog target changes, so
  // it never opens showing the previous member's selection.
  useEffect(() => {
    setRoleSlugs(member?.roles ? [...member.roles] : []);
    setError(undefined);
  }, [member]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!member) return;

    if (roleSlugs.length === 0) {
      setError("Assign at least one role.");
      return;
    }

    try {
      await updateMember.mutateAsync({
        membershipId: member.id,
        payload: { role_slugs: roleSlugs },
      });
      toast.success("Roles updated");
      onOpenChange(false);
    } catch (caught) {
      toast.error("Couldn't update roles", { description: errorMessage(caught) });
      setError(errorMessage(caught));
    }
  }

  return (
    <FormDialog
      open={member !== null}
      onOpenChange={onOpenChange}
      title="Edit roles"
      description={
        member
          ? `Change what ${userDisplayName(member.user)} can do in this workspace.`
          : undefined
      }
      submitLabel="Save roles"
      submitting={updateMember.isPending}
      onSubmit={handleSubmit}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Field id="member-roles-edit" label="Roles" required>
        <RolePicker selected={roleSlugs} onChange={setRoleSlugs} />
      </Field>
    </FormDialog>
  );
}

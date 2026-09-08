"use client";

import { useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { Field, fieldAria } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";

/**
 * Rejection with a reason.
 *
 * The backend requires a reason on `OpportunityRejectRequest`, and it is worth
 * having: the reason is what tells the next reviewer why this publisher was
 * passed over.
 */
export function RejectDialog({
  open,
  onOpenChange,
  title,
  description,
  submitting,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  submitting: boolean;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | undefined>();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const trimmed = reason.trim();
    if (trimmed.length < 3) {
      setError("Give a short reason so the decision is auditable.");
      return;
    }

    setError(undefined);
    await onConfirm(trimmed);
    setReason("");
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setReason("");
          setError(undefined);
        }
        onOpenChange(next);
      }}
      title={title}
      description={description}
      submitLabel="Reject"
      submitting={submitting}
      onSubmit={handleSubmit}
    >
      <Field id="reject-reason" label="Reason" required error={error}>
        <Textarea
          {...fieldAria("reject-reason", { error })}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          placeholder="Low quality directory, irrelevant category, requires payment…"
          autoFocus
        />
      </Field>
    </FormDialog>
  );
}

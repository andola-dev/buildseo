"use client";

import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Spell out the consequence, not just "Are you sure?" (spec §66). */
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => Promise<void> | void;
}

/**
 * Confirmation for a destructive or irreversible action (spec §66).
 *
 * Stays open while the action runs so a slow request can't be double-submitted,
 * and closes only once it resolves. A failure leaves the dialog open — the
 * caller surfaces the error via a toast.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);

  async function handleConfirm(event: React.MouseEvent) {
    event.preventDefault();
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch {
      // Left open deliberately: the user can read the toast and retry.
    } finally {
      setPending(false);
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={pending ? undefined : onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>{description}</div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={pending}
            className={cn(
              destructive && buttonVariants({ variant: "destructive" }),
              destructive && "shadow-xs",
            )}
          >
            {pending ? "Working…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Wire a `ConfirmDialog` without repeating the open/close plumbing. */
export function useConfirmDialog() {
  const [open, setOpen] = useState(false);
  return { open, setOpen, confirm: () => setOpen(true) };
}

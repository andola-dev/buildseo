import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils/cn";

interface FieldProps {
  /** Must match the control's `id` so the label is programmatically bound. */
  id: string;
  label: string;
  /** Client-side or server-mapped error for this field (spec §41). */
  error?: string | undefined;
  hint?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}

/**
 * Label, control, hint and error in one block.
 *
 * Wires `aria-describedby` for hints and errors so screen readers announce
 * them with the control rather than as loose text (spec §44). The control is
 * responsible for its own `aria-invalid`.
 */
export function Field({
  id,
  label,
  error,
  hint,
  required = false,
  className,
  children,
}: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;

  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? (
          <span className="text-destructive" aria-hidden>
            *
          </span>
        ) : null}
      </Label>

      {children}

      {hint && !error ? (
        <p id={hintId} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}

      {error ? (
        <p id={errorId} className="text-destructive text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** The `aria-*` props a control inside a `Field` should spread. */
export function fieldAria(
  id: string,
  { error, hint }: { error?: string | undefined; hint?: string | undefined },
) {
  const describedBy = [hint && !error ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");

  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy || undefined,
  } as const;
}

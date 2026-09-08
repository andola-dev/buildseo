import { Badge } from "@/components/ui/badge";
import { labelFor } from "@/config/labels";
import { statusVariant } from "@/config/status";
import { cn } from "@/lib/utils/cn";

interface StatusBadgeProps {
  /** The backend's raw enum value, e.g. `PENDING_APPROVAL`. */
  status: string | null | undefined;
  /** Label map for this status family; falls back to a humanised value. */
  labels?: Record<string, string>;
  className?: string;
}

/**
 * The one status badge (spec §50).
 *
 * Colour comes from `config/status.ts` and copy from `config/labels.ts`, so a
 * status is styled once and reads identically on every screen. Feature
 * components must not style statuses themselves.
 */
export function StatusBadge({ status, labels, className }: StatusBadgeProps) {
  if (!status) {
    return (
      <Badge variant="muted" className={className}>
        Unknown
      </Badge>
    );
  }

  return (
    <Badge variant={statusVariant(status)} className={cn("uppercase", className)}>
      {labels ? labelFor(labels, status) : status.replace(/_/g, " ")}
    </Badge>
  );
}

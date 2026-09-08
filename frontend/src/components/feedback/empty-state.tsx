import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils/cn";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  /** Say what to do next, not just that there is nothing (spec §38). */
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

/**
 * The empty state for a list or panel.
 *
 * Every major screen supplies its own copy — "No campaigns yet / Create your
 * first campaign to start discovering free listing opportunities" — rather than
 * a bare "No data".
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-14 text-center",
        className,
      )}
    >
      {Icon ? (
        <div className="bg-muted text-muted-foreground flex size-10 items-center justify-center rounded-lg">
          <Icon className="size-5" aria-hidden />
        </div>
      ) : null}

      <div className="space-y-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? (
          <p className="text-muted-foreground mx-auto max-w-sm text-sm">{description}</p>
        ) : null}
      </div>

      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}

import { cn } from "@/lib/utils/cn";
import { formatRelative } from "@/lib/utils/format";
import type { LucideIcon } from "lucide-react";

export interface ActivityItem {
  id: string;
  icon: LucideIcon;
  /** e.g. "Publisher qualified" */
  title: string;
  /** e.g. "example-directory.com" */
  detail?: string | null;
  timestamp: string;
  href?: string;
  tone?: "default" | "success" | "warning" | "danger";
}

const TONE = {
  default: "bg-muted text-muted-foreground",
  success: "bg-success/12 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-destructive/12 text-destructive",
} as const;

/** Recent activity list for the dashboard (spec §18). */
export function ActivityFeed({
  items,
  className,
}: {
  items: readonly ActivityItem[];
  className?: string;
}) {
  return (
    <ul className={cn("divide-y", className)}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <li key={item.id} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
            <span
              className={cn(
                "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md",
                TONE[item.tone ?? "default"],
              )}
            >
              <Icon className="size-3.5" aria-hidden />
            </span>

            <div className="min-w-0 flex-1">
              <div className="text-sm">{item.title}</div>
              {item.detail ? (
                <div className="text-muted-foreground truncate text-xs">{item.detail}</div>
              ) : null}
            </div>

            <time
              dateTime={item.timestamp}
              className="text-muted-foreground shrink-0 text-xs whitespace-nowrap"
            >
              {formatRelative(item.timestamp)}
            </time>
          </li>
        );
      })}
    </ul>
  );
}

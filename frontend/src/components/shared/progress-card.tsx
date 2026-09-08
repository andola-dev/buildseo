import Link from "next/link";

import { Progress } from "@/components/ui/progress";
import { formatNumber, formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

interface ProgressCardProps {
  title: string;
  subtitle?: string;
  current: number;
  /** `null` when the campaign has no link target set. */
  target: number | null | undefined;
  unit?: string;
  href?: string;
  className?: string;
}

/**
 * Progress toward a campaign's link target (spec §18).
 *
 * With no target set the bar is omitted rather than shown at 0%, which would
 * read as failure rather than as "not applicable".
 */
export function ProgressCard({
  title,
  subtitle,
  current,
  target,
  unit = "Links",
  href,
  className,
}: ProgressCardProps) {
  const hasTarget = typeof target === "number" && target > 0;
  const percent = hasTarget ? Math.min(100, (current / target) * 100) : null;

  const heading = href ? (
    <Link href={href} className="font-medium hover:underline">
      {title}
    </Link>
  ) : (
    <span className="font-medium">{title}</span>
  );

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm">{heading}</div>
          {subtitle ? (
            <div className="text-muted-foreground truncate text-xs">{subtitle}</div>
          ) : null}
        </div>
        <div className="text-right whitespace-nowrap">
          <div className="tabular text-sm font-semibold">
            {formatNumber(current)}
            {hasTarget ? (
              <span className="text-muted-foreground font-normal"> / {formatNumber(target)}</span>
            ) : null}
          </div>
          <div className="text-muted-foreground text-xs">
            {percent === null ? `${unit} · no target` : `${formatPercent(percent)} complete`}
          </div>
        </div>
      </div>

      {percent === null ? null : (
        <Progress
          value={percent}
          className="h-1.5"
          aria-label={`${title}: ${formatNumber(current)} of ${formatNumber(target)} ${unit}`}
        />
      )}
    </div>
  );
}

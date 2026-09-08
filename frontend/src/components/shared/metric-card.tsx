import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils/cn";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  /** Short qualifier under the number, e.g. "across 3 campaigns". */
  hint?: string;
  href?: string;
  className?: string;
}

/** A single KPI figure for the dashboard (spec §18). */
export function MetricCard({
  label,
  value,
  icon: Icon,
  hint,
  href,
  className,
}: MetricCardProps) {
  const content = (
    <Card
      className={cn(
        "h-full transition-colors",
        href && "hover:border-ring/60 hover:bg-accent/30",
        className,
      )}
    >
      <CardHeader className="pb-0">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {label}
          </CardTitle>
          {Icon ? (
            <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <div className="tabular text-2xl font-semibold tracking-tight">{value}</div>
        {hint ? (
          <p className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
            {hint}
            {href ? <ArrowRight className="size-3" aria-hidden /> : null}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );

  if (!href) return content;

  return (
    <Link
      href={href}
      className="rounded-lg focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {content}
    </Link>
  );
}

import { cn } from "@/lib/utils/cn";

interface PageHeaderProps {
  title: string;
  description?: string;
  /** Primary and secondary actions, right-aligned on wide screens. */
  actions?: React.ReactNode;
  /** Status badges or scope indicators shown beside the title. */
  badges?: React.ReactNode;
  className?: string;
}

/** The heading block at the top of every page (spec §51). */
export function PageHeader({
  title,
  description,
  actions,
  badges,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 pb-6 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
          {badges}
        </div>
        {description ? (
          <p className="text-muted-foreground max-w-2xl text-sm">{description}</p>
        ) : null}
      </div>

      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

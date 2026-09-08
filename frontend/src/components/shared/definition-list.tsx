import { EM_DASH } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

export interface DefinitionItem {
  label: string;
  /** `null`/`undefined` renders an em dash rather than an empty row. */
  value: React.ReactNode;
}

/**
 * Label/value pairs for detail panels.
 *
 * A real `<dl>` so the label-value relationship is available to screen readers
 * rather than only visually implied (spec §44).
 */
export function DefinitionList({
  items,
  className,
}: {
  items: readonly DefinitionItem[];
  className?: string;
}) {
  return (
    <dl className={cn("divide-y text-sm", className)}>
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-muted-foreground shrink-0 text-xs">{item.label}</dt>
          <dd className="min-w-0 truncate text-right font-medium">
            {item.value === null || item.value === undefined || item.value === ""
              ? EM_DASH
              : item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

"use client";

import { useState } from "react";
import { CalendarIcon, X } from "lucide-react";
import type { DateRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatDate } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

interface DateRangePickerProps {
  /** ISO date strings, as the audit filters carry them in the URL. */
  from: string | null;
  to: string | null;
  onChange: (range: { from: string | null; to: string | null }) => void;
  label?: string;
  className?: string;
}

function toDate(value: string | null): Date | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function toIso(date: Date | undefined): string | null {
  return date ? date.toISOString() : null;
}

/** Date-range filter used by the audit log and AI usage screens (spec §36). */
export function DateRangePicker({
  from,
  to,
  onChange,
  label = "Date range",
  className,
}: DateRangePickerProps) {
  const [open, setOpen] = useState(false);

  const selected: DateRange | undefined = from || to
    ? { from: toDate(from), to: toDate(to) }
    : undefined;

  const hasRange = Boolean(from || to);

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5 font-normal">
            <CalendarIcon className="size-3.5 opacity-70" aria-hidden />
            {hasRange ? (
              <span>
                {from ? formatDate(from) : "Any"} → {to ? formatDate(to) : "Any"}
              </span>
            ) : (
              <span className="text-muted-foreground">{label}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="range"
            numberOfMonths={2}
            defaultMonth={toDate(from)}
            selected={selected}
            onSelect={(range) =>
              onChange({ from: toIso(range?.from), to: toIso(range?.to) })
            }
          />
        </PopoverContent>
      </Popover>

      {hasRange ? (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onChange({ from: null, to: null })}
        >
          <X className="size-3.5" aria-hidden />
          <span className="sr-only">Clear date range</span>
        </Button>
      ) : null}
    </div>
  );
}

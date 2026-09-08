"use client";

import { Check, ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils/cn";

export interface FilterOption {
  value: string;
  label: string;
}

interface FilterDropdownProps {
  label: string;
  options: readonly FilterOption[];
  /** `null` means "no filter". */
  value: string | null;
  onChange: (value: string | null) => void;
  className?: string;
}

/**
 * Single-select filter for a table toolbar.
 *
 * The trigger shows the selected label so the active filter is readable without
 * opening the menu, and "Any" clears it.
 */
export function FilterDropdown({
  label,
  options,
  value,
  onChange,
  className,
}: FilterDropdownProps) {
  const selected = options.find((option) => option.value === value) ?? null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn("gap-1.5 font-normal", className)}
        >
          <span className="text-muted-foreground">{label}</span>
          {selected ? (
            <Badge variant="secondary" className="rounded-sm px-1 font-medium">
              {selected.label}
            </Badge>
          ) : (
            <span>Any</span>
          )}
          <ChevronDown className="size-3.5 opacity-50" aria-hidden />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="max-h-72 w-56 overflow-y-auto">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onChange(null)}>
          <Check className={cn("size-4", value !== null && "invisible")} aria-hidden />
          Any
        </DropdownMenuItem>
        {options.map((option) => (
          <DropdownMenuItem key={option.value} onSelect={() => onChange(option.value)}>
            <Check
              className={cn("size-4", value !== option.value && "invisible")}
              aria-hidden
            />
            {option.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Build filter options from an enum value list and its label map. */
export function optionsFromEnum(
  values: readonly string[],
  labels: Record<string, string>,
): FilterOption[] {
  return values.map((value) => ({ value, label: labels[value] ?? value }));
}

"use client";

import { X } from "lucide-react";
import type { Table } from "@tanstack/react-table";

import { Button } from "@/components/ui/button";
import { DataTableViewOptions } from "@/components/data-table/data-table-view-options";
import { cn } from "@/lib/utils/cn";

interface DataTableToolbarProps<TData> {
  table: Table<TData>;
  /** The `SearchInput`, rendered first. */
  search?: React.ReactNode;
  /** `FilterDropdown`s and other filter controls. */
  filters?: React.ReactNode;
  /** How many filters are set, for the reset affordance. */
  activeFilterCount?: number;
  onResetFilters?: () => void;
  /** Bulk actions shown when rows are selected. */
  selectionActions?: React.ReactNode;
  className?: string;
}

/**
 * The controls above a table (spec §17/§51).
 *
 * Filter state itself lives in the URL — the toolbar only renders controls and
 * reports changes upward, so it stays reusable across every list screen.
 */
export function DataTableToolbar<TData>({
  table,
  search,
  filters,
  activeFilterCount = 0,
  onResetFilters,
  selectionActions,
  className,
}: DataTableToolbarProps<TData>) {
  const selectedCount = table.getFilteredSelectedRowModel().rows.length;

  return (
    <div className={cn("flex flex-col gap-2 pb-3 lg:flex-row lg:items-center", className)}>
      <div className="flex flex-1 flex-wrap items-center gap-2">
        {search}
        {filters}

        {activeFilterCount > 0 && onResetFilters ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={onResetFilters}
            className="text-muted-foreground gap-1 font-normal"
          >
            <X className="size-3.5" aria-hidden />
            Clear
            {activeFilterCount > 1 ? ` (${activeFilterCount})` : null}
          </Button>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        {selectedCount > 0 && selectionActions ? (
          <div className="flex items-center gap-2 border-r pr-2">{selectionActions}</div>
        ) : null}
        <DataTableViewOptions table={table} />
      </div>
    </div>
  );
}

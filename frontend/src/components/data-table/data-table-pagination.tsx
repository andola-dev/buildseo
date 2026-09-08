"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PAGE_SIZE_OPTIONS } from "@/config/app";
import { formatNumber } from "@/lib/utils/format";
import type { PaginationMeta } from "@/types/api";

interface DataTablePaginationProps {
  meta: PaginationMeta;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  /** Shown when rows are selectable, e.g. "3 of 25 selected". */
  selectionLabel?: string;
}

/**
 * Server-side pagination footer (spec §54).
 *
 * The counters come from the backend's `PaginationMeta`; the table never holds
 * more than one page of rows, so a large publisher database stays usable.
 */
export function DataTablePagination({
  meta,
  onPageChange,
  onPageSizeChange,
  selectionLabel,
}: DataTablePaginationProps) {
  const first = meta.total === 0 ? 0 : (meta.page - 1) * meta.page_size + 1;
  const last = Math.min(meta.page * meta.page_size, meta.total);

  return (
    <div className="flex flex-col-reverse items-center justify-between gap-3 px-1 py-3 sm:flex-row">
      <div className="text-muted-foreground text-sm">
        {selectionLabel ? (
          <span>{selectionLabel}</span>
        ) : (
          <span>
            {meta.total === 0
              ? "No results"
              : `${formatNumber(first)}–${formatNumber(last)} of ${formatNumber(meta.total)}`}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground hidden text-sm sm:inline">Rows</span>
          <Select
            value={String(meta.page_size)}
            onValueChange={(value) => onPageSizeChange(Number.parseInt(value, 10))}
          >
            <SelectTrigger size="sm" className="w-[4.5rem]" aria-label="Rows per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-muted-foreground mr-1 hidden text-sm md:inline">
            Page {meta.page} of {Math.max(meta.total_pages, 1)}
          </span>

          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(1)}
            disabled={!meta.has_previous}
            aria-label="First page"
          >
            <ChevronsLeft className="size-4" aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(meta.page - 1)}
            disabled={!meta.has_previous}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(meta.page + 1)}
            disabled={!meta.has_next}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(meta.total_pages)}
            disabled={!meta.has_next}
            aria-label="Last page"
          >
            <ChevronsRight className="size-4" aria-hidden />
          </Button>
        </div>
      </div>
    </div>
  );
}

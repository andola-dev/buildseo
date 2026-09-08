"use client";

import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type RowSelectionState,
  type SortingState,
  type Table as TanstackTable,
  type VisibilityState,
} from "@tanstack/react-table";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useIsMobile } from "@/hooks/use-media-query";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/loading-state";
import { cn } from "@/lib/utils/cn";

export interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  /** Stable row id, required for selection to survive refetches. */
  getRowId: (row: TData) => string;

  isLoading?: boolean;
  isFetching?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** What the table shows, for the error copy: "your publishers". */
  resourceLabel?: string;

  /** Rendered when there are no rows and no error. */
  emptyState?: React.ReactNode;

  /**
   * Server-side sorting. Sorting is delegated to the backend because only one
   * page of rows is in the browser (spec §54), so sorting locally would only
   * reorder the current page.
   */
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;

  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;

  columnVisibility?: VisibilityState;
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>;

  /** Toolbar and pagination, given the table instance. */
  toolbar?: (table: TanstackTable<TData>) => React.ReactNode;
  footer?: (table: TanstackTable<TData>) => React.ReactNode;

  onRowClick?: (row: TData) => void;

  /**
   * Card renderer used below `md`, where a wide table cannot work (spec §43).
   * Without one the table falls back to a bounded horizontal scroll region.
   *
   * Only the applicable variant is rendered — switching with CSS would keep
   * both in the DOM, doubling the node count for a 100-row table.
   */
  mobileRow?: (row: TData) => React.ReactNode;

  className?: string;
}

/**
 * The single table implementation (spec §17).
 *
 * TanStack Table owns the row/column model; sorting, filtering and pagination
 * are server-driven and passed in as controlled state, which is what keeps
 * table state shareable through the URL. No feature builds its own table.
 */
export function DataTable<TData>({
  columns,
  data,
  getRowId,
  isLoading = false,
  isFetching = false,
  error,
  onRetry,
  resourceLabel,
  emptyState,
  sorting,
  onSortingChange,
  rowSelection,
  onRowSelectionChange,
  columnVisibility,
  onColumnVisibilityChange,
  toolbar,
  footer,
  onRowClick,
  mobileRow,
  className,
}: DataTableProps<TData>) {
  const isMobile = useIsMobile();
  const useCards = isMobile && Boolean(mobileRow);

  const table = useReactTable({
    data,
    columns,
    getRowId,
    getCoreRowModel: getCoreRowModel(),

    // Everything below is resolved by the backend; the table must not re-do it
    // on the current page or the two would disagree.
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,

    state: {
      ...(sorting ? { sorting } : {}),
      ...(rowSelection ? { rowSelection } : {}),
      ...(columnVisibility ? { columnVisibility } : {}),
    },
    ...(onSortingChange ? { onSortingChange } : {}),
    ...(onRowSelectionChange ? { onRowSelectionChange } : {}),
    ...(onColumnVisibilityChange ? { onColumnVisibilityChange } : {}),
    enableRowSelection: Boolean(onRowSelectionChange),
  });

  const rows = table.getRowModel().rows;
  const visibleColumnCount = table.getVisibleLeafColumns().length;

  const toolbarNode = useMemo(() => toolbar?.(table), [toolbar, table]);

  if (error) {
    return (
      <div className={className}>
        {toolbarNode}
        <div className="rounded-lg border">
          <ErrorState error={error} {...(resourceLabel ? { resource: resourceLabel } : {})} {...(onRetry ? { onRetry } : {})} />
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className={className}>
        {toolbarNode}
        <TableSkeleton columns={Math.max(visibleColumnCount, 4)} />
      </div>
    );
  }

  return (
    <div className={className}>
      {toolbarNode}

      {/* Below `md` a 12-column table would force the page into horizontal
          scroll, so rows become stacked record cards instead (spec §43). */}
      {useCards ? (
        <div className="space-y-2">
          {rows.length === 0
            ? (emptyState ?? null)
            : rows.map((row) => (
                <div
                  key={row.id}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  className={cn("rounded-lg border p-3", onRowClick && "cursor-pointer")}
                >
                  {mobileRow?.(row.original)}
                </div>
              ))}
        </div>
      ) : (
      <div
        className={cn(
          "relative overflow-x-auto rounded-lg border",
          isFetching && "opacity-70 transition-opacity",
        )}
      >
        {/* A background refetch dims the table rather than replacing it with a
            skeleton, so the user's place isn't lost. */}
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    style={
                      header.column.columnDef.size
                        ? { width: header.column.columnDef.size }
                        : undefined
                    }
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {rows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={visibleColumnCount} className="p-0">
                  {emptyState ?? null}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() ? "selected" : undefined}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  className={cn(onRowClick && "cursor-pointer")}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      )}

      {footer?.(table)}
    </div>
  );
}

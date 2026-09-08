"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import type { Column } from "@tanstack/react-table";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

/**
 * A sortable column header.
 *
 * Renders plain text for a column that isn't sortable, so a non-interactive
 * header is not announced as a button.
 */
export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
}) {
  if (!column.getCanSort()) {
    return <span className={cn("text-xs font-medium", className)}>{title}</span>;
  }

  const sorted = column.getIsSorted();
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ChevronsUpDown;

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => column.toggleSorting(sorted === "asc")}
      className={cn("-ml-2 h-7 gap-1 px-2 text-xs font-medium", className)}
      aria-label={`Sort by ${title}`}
    >
      {title}
      <Icon className={cn("size-3.5", !sorted && "opacity-40")} aria-hidden />
    </Button>
  );
}

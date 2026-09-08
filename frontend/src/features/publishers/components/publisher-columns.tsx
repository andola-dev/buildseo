"use client";

import Link from "next/link";
import { ExternalLink, MoreHorizontal } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DataTableColumnHeader, selectColumn } from "@/components/data-table";
import { ScoreBadge } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { labelFor, PUBLISHER_CATEGORY_LABELS, PUBLISHER_STATUS_LABELS, SUBMISSION_METHOD_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { displayDomain, formatCompactNumber } from "@/lib/utils/format";
import type { Publisher } from "@/types/api";

export interface PublisherRowActions {
  onQualify: (publisher: Publisher) => void;
  onDelete: (publisher: Publisher) => void;
  can: (permission: string) => boolean;
}

/**
 * Columns for the publisher database (spec §22).
 *
 * The metric columns are the reason this screen exists, so they lead with the
 * scores and stay numeric and scannable — `tabular` keeps the digits aligned.
 */
export function publisherColumns(
  actions: PublisherRowActions,
): ColumnDef<Publisher, unknown>[] {
  return [
    selectColumn<Publisher>(),
    {
      accessorKey: "name",
      meta: { label: "Publisher" },
      enableHiding: false,
      header: ({ column }) => <DataTableColumnHeader column={column} title="Publisher" />,
      cell: ({ row }) => (
        <div className="min-w-0 max-w-56">
          <Link
            href={`/publishers/${row.original.id}`}
            className="block truncate font-medium hover:underline"
          >
            {row.original.name ?? displayDomain(row.original.domain)}
          </Link>
          <div className="text-muted-foreground truncate text-xs">
            {displayDomain(row.original.domain)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "category",
      meta: { label: "Category" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Category" />,
      cell: ({ row }) => (
        <span className="text-sm">
          {labelFor(PUBLISHER_CATEGORY_LABELS, row.original.category)}
        </span>
      ),
    },
    {
      accessorKey: "country",
      meta: { label: "Country" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Country" />,
      cell: ({ row }) => row.original.country?.toUpperCase() ?? "—",
    },
    {
      accessorKey: "authority_score",
      meta: { label: "Authority" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Authority" />,
      cell: ({ row }) => (
        <ScoreBadge score={row.original.authority_score} kind="authority" />
      ),
    },
    {
      accessorKey: "organic_traffic",
      meta: { label: "Traffic" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Traffic" />,
      cell: ({ row }) => (
        <span className="tabular text-sm">
          {formatCompactNumber(row.original.organic_traffic)}
        </span>
      ),
    },
    {
      accessorKey: "relevance_score",
      meta: { label: "Relevance" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Relevance" />,
      cell: ({ row }) => (
        <ScoreBadge score={row.original.relevance_score} kind="relevance" />
      ),
    },
    {
      accessorKey: "spam_score",
      meta: { label: "Spam" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Spam" />,
      cell: ({ row }) => <ScoreBadge score={row.original.spam_score} kind="spam" />,
    },
    {
      accessorKey: "quality_score",
      meta: { label: "Quality" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Quality" />,
      cell: ({ row }) => <ScoreBadge score={row.original.quality_score} kind="quality" />,
    },
    {
      accessorKey: "submission_method",
      meta: { label: "Submission" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Submission" />,
      cell: ({ row }) => (
        <div className="flex items-center gap-1.5">
          <span className="text-sm">
            {labelFor(SUBMISSION_METHOD_LABELS, row.original.submission_method)}
          </span>
          {row.original.dofollow_supported ? (
            <Badge variant="success" className="px-1">
              DF
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      accessorKey: "status",
      meta: { label: "Status" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => (
        <StatusBadge status={row.original.status} labels={PUBLISHER_STATUS_LABELS} />
      ),
    },
    {
      id: "actions",
      size: 48,
      enableHiding: false,
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const publisher = row.original;

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => event.stopPropagation()}
                aria-label={`Actions for ${publisher.name ?? publisher.domain}`}
              >
                <MoreHorizontal className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link href={`/publishers/${publisher.id}`}>View details</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a href={publisher.website_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4" aria-hidden />
                  Open site
                </a>
              </DropdownMenuItem>
              {publisher.submission_url ? (
                <DropdownMenuItem asChild>
                  <a
                    href={publisher.submission_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink className="size-4" aria-hidden />
                    Open submission page
                  </a>
                </DropdownMenuItem>
              ) : null}

              {actions.can(PERM.PUBLISHER_QUALIFY) ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => actions.onQualify(publisher)}>
                    Re-qualify
                  </DropdownMenuItem>
                </>
              ) : null}

              {actions.can(PERM.PUBLISHER_DELETE) ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => actions.onDelete(publisher)}
                  >
                    Delete
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];
}

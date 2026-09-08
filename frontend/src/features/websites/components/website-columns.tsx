"use client";

import Link from "next/link";
import { ExternalLink, MoreHorizontal } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DataTableColumnHeader } from "@/components/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { CLIENT_WEBSITE_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { displayDomain, formatDate } from "@/lib/utils/format";
import type { ClientWebsite } from "@/types/api";

export interface WebsiteRowActions {
  onArchive: (website: ClientWebsite) => void;
  onDelete: (website: ClientWebsite) => void;
  can: (permission: string) => boolean;
}

/**
 * Column definitions for the client-website table.
 *
 * Defined outside the component so the array identity is stable across
 * renders, which is what stops TanStack Table rebuilding its column model on
 * every keystroke in the search box.
 */
export function websiteColumns(actions: WebsiteRowActions): ColumnDef<ClientWebsite, unknown>[] {
  return [
    {
      accessorKey: "name",
      meta: { label: "Website" },
      enableHiding: false,
      header: ({ column }) => <DataTableColumnHeader column={column} title="Website" />,
      cell: ({ row }) => (
        <div className="min-w-0">
          <Link
            href={`/websites/${row.original.id}`}
            className="font-medium hover:underline"
          >
            {row.original.name}
          </Link>
          <div className="text-muted-foreground truncate text-xs">
            {displayDomain(row.original.website_url)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "industry",
      meta: { label: "Industry" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Industry" />,
      cell: ({ row }) => row.original.industry ?? "—",
    },
    {
      accessorKey: "target_country",
      meta: { label: "Country" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Country" />,
      cell: ({ row }) => row.original.target_country?.toUpperCase() ?? "—",
    },
    {
      accessorKey: "status",
      meta: { label: "Status" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => (
        <StatusBadge status={row.original.status} labels={CLIENT_WEBSITE_STATUS_LABELS} />
      ),
    },
    {
      accessorKey: "created_at",
      meta: { label: "Created" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ row }) => (
        <span className="tabular text-sm">{formatDate(row.original.created_at)}</span>
      ),
    },
    {
      id: "actions",
      size: 48,
      enableHiding: false,
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const website = row.original;
        const canUpdate = actions.can(PERM.CLIENT_WEBSITE_UPDATE);
        const canDelete = actions.can(PERM.CLIENT_WEBSITE_DELETE);

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => event.stopPropagation()}
                aria-label={`Actions for ${website.name}`}
              >
                <MoreHorizontal className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem asChild>
                <Link href={`/websites/${website.id}`}>View</Link>
              </DropdownMenuItem>
              {canUpdate ? (
                <DropdownMenuItem asChild>
                  <Link href={`/websites/${website.id}?edit=1`}>Edit</Link>
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem asChild>
                <a href={website.website_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4" aria-hidden />
                  Open site
                </a>
              </DropdownMenuItem>

              {canUpdate && website.status !== "ARCHIVED" ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => actions.onArchive(website)}>
                    Archive
                  </DropdownMenuItem>
                </>
              ) : null}

              {canDelete ? (
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => actions.onDelete(website)}
                >
                  Delete
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];
}

"use client";

import Link from "next/link";
import { MoreHorizontal } from "lucide-react";
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
import { CAMPAIGN_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { formatDate, formatNumber } from "@/lib/utils/format";
import type { Campaign, CampaignStatus } from "@/types/api";

export interface CampaignRowActions {
  onStatusChange: (campaign: Campaign, status: CampaignStatus) => void;
  onDelete: (campaign: Campaign) => void;
  can: (permission: string) => boolean;
  /** Resolves a website id to its name for the Website column. */
  websiteName: (websiteId: string) => string;
}

/**
 * Status transitions offered per current status.
 *
 * The list is intentionally conservative: the backend validates the change, and
 * offering only sensible next states avoids inviting a rejection.
 */
function nextStatuses(status: string): CampaignStatus[] {
  switch (status) {
    case "DRAFT":
      return ["ACTIVE", "ARCHIVED"];
    case "ACTIVE":
      return ["PAUSED", "COMPLETED"];
    case "PAUSED":
      return ["ACTIVE", "ARCHIVED"];
    case "COMPLETED":
      return ["ARCHIVED"];
    default:
      return [];
  }
}

export function campaignColumns(
  actions: CampaignRowActions,
): ColumnDef<Campaign, unknown>[] {
  return [
    {
      accessorKey: "name",
      meta: { label: "Campaign" },
      enableHiding: false,
      header: ({ column }) => <DataTableColumnHeader column={column} title="Campaign" />,
      cell: ({ row }) => (
        <Link
          href={`/campaigns/${row.original.id}`}
          className="font-medium hover:underline"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      accessorKey: "client_website_id",
      meta: { label: "Website" },
      enableSorting: false,
      header: () => <span className="text-xs font-medium">Website</span>,
      cell: ({ row }) => (
        <Link
          href={`/websites/${row.original.client_website_id}`}
          className="text-muted-foreground text-sm hover:underline"
        >
          {actions.websiteName(row.original.client_website_id)}
        </Link>
      ),
    },
    {
      accessorKey: "status",
      meta: { label: "Status" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => (
        <StatusBadge status={row.original.status} labels={CAMPAIGN_STATUS_LABELS} />
      ),
    },
    {
      accessorKey: "target_link_count",
      meta: { label: "Target links" },
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Target links" />
      ),
      cell: ({ row }) => (
        <span className="tabular text-sm">
          {row.original.target_link_count === null ||
          row.original.target_link_count === undefined
            ? "—"
            : formatNumber(row.original.target_link_count)}
        </span>
      ),
    },
    {
      accessorKey: "target_country",
      meta: { label: "Country" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Country" />,
      cell: ({ row }) => row.original.target_country?.toUpperCase() ?? "—",
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
        const campaign = row.original;
        const canUpdate = actions.can(PERM.CAMPAIGN_UPDATE);
        const transitions = canUpdate ? nextStatuses(campaign.status) : [];

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => event.stopPropagation()}
                aria-label={`Actions for ${campaign.name}`}
              >
                <MoreHorizontal className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link href={`/campaigns/${campaign.id}`}>View</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href={`/opportunities?campaign_id=${campaign.id}`}>
                  View opportunities
                </Link>
              </DropdownMenuItem>

              {transitions.length > 0 ? (
                <>
                  <DropdownMenuSeparator />
                  {transitions.map((status) => (
                    <DropdownMenuItem
                      key={status}
                      onSelect={() => actions.onStatusChange(campaign, status)}
                    >
                      Mark {CAMPAIGN_STATUS_LABELS[status].toLowerCase()}
                    </DropdownMenuItem>
                  ))}
                </>
              ) : null}

              {actions.can(PERM.CAMPAIGN_DELETE) ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => actions.onDelete(campaign)}
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

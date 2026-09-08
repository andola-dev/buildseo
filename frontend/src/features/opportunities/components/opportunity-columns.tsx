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
import { DataTableColumnHeader } from "@/components/data-table";
import { ScoreBadge } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  labelFor,
  OPPORTUNITY_STATUS_LABELS,
  OPPORTUNITY_TYPE_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import { displayDomain, truncate } from "@/lib/utils/format";
import type { Opportunity } from "@/types/api";

export interface OpportunityRowActions {
  onSelect: (opportunity: Opportunity) => void;
  onReject: (opportunity: Opportunity) => void;
  onPrepare: (opportunity: Opportunity) => void;
  can: (permission: string) => boolean;
  campaignName: (campaignId: string) => string;
}

/** Priority is an integer; show it as a band so it reads at a glance. */
function priorityBadge(priority: number) {
  if (priority >= 80) return <Badge variant="destructive">Critical</Badge>;
  if (priority >= 60) return <Badge variant="warning">High</Badge>;
  if (priority >= 30) return <Badge variant="info">Medium</Badge>;
  return <Badge variant="muted">Low</Badge>;
}

/** Columns for the opportunities workflow table (spec §25). */
export function opportunityColumns(
  actions: OpportunityRowActions,
): ColumnDef<Opportunity, unknown>[] {
  return [
    {
      accessorKey: "suggested_title",
      meta: { label: "Opportunity" },
      enableHiding: false,
      header: ({ column }) => <DataTableColumnHeader column={column} title="Opportunity" />,
      cell: ({ row }) => (
        <div className="min-w-0 max-w-64">
          <Link
            href={`/opportunities/${row.original.id}`}
            className="block truncate font-medium hover:underline"
          >
            {row.original.suggested_title ?? "Untitled listing"}
          </Link>
          <div className="text-muted-foreground truncate text-xs">
            {displayDomain(row.original.target_url)}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "campaign_id",
      meta: { label: "Campaign" },
      enableSorting: false,
      header: () => <span className="text-xs font-medium">Campaign</span>,
      cell: ({ row }) => (
        <Link
          href={`/campaigns/${row.original.campaign_id}`}
          className="text-muted-foreground text-sm hover:underline"
        >
          {actions.campaignName(row.original.campaign_id)}
        </Link>
      ),
    },
    {
      accessorKey: "opportunity_type",
      meta: { label: "Type" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
      cell: ({ row }) => (
        <span className="text-sm">
          {labelFor(OPPORTUNITY_TYPE_LABELS, row.original.opportunity_type)}
        </span>
      ),
    },
    {
      accessorKey: "qualification_score",
      meta: { label: "Score" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Score" />,
      cell: ({ row }) => (
        <ScoreBadge score={row.original.qualification_score} kind="opportunity" />
      ),
    },
    {
      accessorKey: "priority",
      meta: { label: "Priority" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Priority" />,
      cell: ({ row }) => priorityBadge(row.original.priority),
    },
    {
      accessorKey: "category",
      meta: { label: "Category" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Category" />,
      cell: ({ row }) => row.original.category ?? "—",
    },
    {
      accessorKey: "target_url",
      meta: { label: "Target URL" },
      enableSorting: false,
      header: () => <span className="text-xs font-medium">Target URL</span>,
      cell: ({ row }) => (
        <a
          href={row.original.target_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => event.stopPropagation()}
          className="text-muted-foreground inline-flex items-center gap-1 text-sm hover:underline"
        >
          {truncate(displayDomain(row.original.target_url), 32)}
          <ExternalLink className="size-3" aria-hidden />
        </a>
      ),
    },
    {
      accessorKey: "status",
      meta: { label: "Status" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => (
        <StatusBadge status={row.original.status} labels={OPPORTUNITY_STATUS_LABELS} />
      ),
    },
    {
      id: "actions",
      size: 48,
      enableHiding: false,
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const opportunity = row.original;
        const canUpdate = actions.can(PERM.OPPORTUNITY_UPDATE);
        const canCreateSubmission = actions.can(PERM.SUBMISSION_CREATE);

        // Which actions make sense depends on where the opportunity is in the
        // workflow; the backend validates the transition regardless.
        const canApprove = canUpdate && ["DISCOVERED", "QUALIFIED"].includes(opportunity.status);
        const canReject =
          canUpdate && !["REJECTED", "PUBLISHED", "SUBMITTED"].includes(opportunity.status);
        const canPrepare =
          canCreateSubmission && ["SELECTED", "READY"].includes(opportunity.status);

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => event.stopPropagation()}
                aria-label="Opportunity actions"
              >
                <MoreHorizontal className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link href={`/opportunities/${opportunity.id}`}>View details</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href={`/publishers/${opportunity.publisher_id}`}>View publisher</Link>
              </DropdownMenuItem>

              {canApprove || canReject || canPrepare ? <DropdownMenuSeparator /> : null}

              {canApprove ? (
                <DropdownMenuItem onSelect={() => actions.onSelect(opportunity)}>
                  Approve
                </DropdownMenuItem>
              ) : null}

              {canPrepare ? (
                <DropdownMenuItem onSelect={() => actions.onPrepare(opportunity)}>
                  Prepare submission
                </DropdownMenuItem>
              ) : null}

              {canReject ? (
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => actions.onReject(opportunity)}
                >
                  Reject
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];
}

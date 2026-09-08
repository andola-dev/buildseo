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
import {
  labelFor,
  SUBMISSION_METHOD_LABELS,
  SUBMISSION_STATUS_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import { displayDomain, formatDateTime, truncate } from "@/lib/utils/format";
import type { Submission } from "@/types/api";

export interface SubmissionRowActions {
  onApprove: (submission: Submission) => void;
  onReject: (submission: Submission) => void;
  onVerify: (submission: Submission) => void;
  can: (permission: string) => boolean;
  campaignName: (campaignId: string) => string;
}

/** Columns for the submissions table (spec §28). */
export function submissionColumns(
  actions: SubmissionRowActions,
): ColumnDef<Submission, unknown>[] {
  return [
    {
      accessorKey: "submitted_title",
      meta: { label: "Submission" },
      enableHiding: false,
      header: ({ column }) => <DataTableColumnHeader column={column} title="Submission" />,
      cell: ({ row }) => (
        <div className="min-w-0 max-w-64">
          <Link
            href={`/submissions/${row.original.id}`}
            className="block truncate font-medium hover:underline"
          >
            {row.original.submitted_title ?? "Untitled submission"}
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
      accessorKey: "anchor_text",
      meta: { label: "Anchor" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Anchor" />,
      cell: ({ row }) => (
        <span className="text-sm">{truncate(row.original.anchor_text, 28)}</span>
      ),
    },
    {
      accessorKey: "submission_method",
      meta: { label: "Method" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Method" />,
      cell: ({ row }) => (
        <span className="text-sm">
          {labelFor(SUBMISSION_METHOD_LABELS, row.original.submission_method)}
        </span>
      ),
    },
    {
      accessorKey: "status",
      meta: { label: "Status" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => (
        <StatusBadge status={row.original.status} labels={SUBMISSION_STATUS_LABELS} />
      ),
    },
    {
      accessorKey: "submitted_at",
      meta: { label: "Submitted" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Submitted" />,
      cell: ({ row }) => (
        <span className="tabular text-sm">
          {row.original.submitted_at ? formatDateTime(row.original.submitted_at) : "—"}
        </span>
      ),
    },
    {
      accessorKey: "published_at",
      meta: { label: "Published" },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Published" />,
      cell: ({ row }) => (
        <span className="tabular text-sm">
          {row.original.published_at ? formatDateTime(row.original.published_at) : "—"}
        </span>
      ),
    },
    {
      id: "actions",
      size: 48,
      enableHiding: false,
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const submission = row.original;

        const canApprove =
          actions.can(PERM.SUBMISSION_APPROVE) &&
          ["READY", "PENDING_APPROVAL"].includes(submission.status);
        const canReject =
          actions.can(PERM.SUBMISSION_APPROVE) &&
          !["REJECTED", "VERIFIED", "FAILED"].includes(submission.status);
        const canVerify =
          actions.can(PERM.SUBMISSION_VERIFY) &&
          ["SUBMITTED", "PUBLISHED", "VERIFICATION_PENDING"].includes(submission.status);

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => event.stopPropagation()}
                aria-label="Submission actions"
              >
                <MoreHorizontal className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link href={`/submissions/${submission.id}`}>Review</Link>
              </DropdownMenuItem>
              {submission.submitted_url ? (
                <DropdownMenuItem asChild>
                  <a
                    href={submission.submitted_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink className="size-4" aria-hidden />
                    Open live listing
                  </a>
                </DropdownMenuItem>
              ) : null}

              {canApprove || canVerify || canReject ? <DropdownMenuSeparator /> : null}

              {canApprove ? (
                <DropdownMenuItem onSelect={() => actions.onApprove(submission)}>
                  Approve
                </DropdownMenuItem>
              ) : null}

              {canVerify ? (
                <DropdownMenuItem onSelect={() => actions.onVerify(submission)}>
                  Verify link
                </DropdownMenuItem>
              ) : null}

              {canReject ? (
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => actions.onReject(submission)}
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

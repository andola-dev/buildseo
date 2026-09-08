"use client";

import { useMemo, useState } from "react";
import { ScrollText } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { DefinitionList } from "@/components/shared/definition-list";
import { SearchInput } from "@/components/shared/search-input";
import { humanizeEnum } from "@/config/labels";
import { useAuditLogs } from "@/features/audit/api/use-audit";
import { useMembers } from "@/features/team/api/use-team";
import { FilterDropdown } from "@/components/shared/filter-dropdown";
import { useListState } from "@/hooks/use-list-state";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { PERM } from "@/config/permissions";
import { formatDateTime, truncate, userDisplayName } from "@/lib/utils/format";
import type { AuditLog } from "@/types/api";

const FILTER_KEYS = ["action", "user_id", "resource_type", "since", "until"] as const;

/** Action verbs that changed something, shown in a stronger tone. */
function actionTone(action: string): "success" | "danger" | "muted" | "info" {
  if (action.includes("delete") || action.includes("reject")) return "danger";
  if (action.includes("create") || action.includes("approve")) return "success";
  if (action.includes("update") || action.includes("verify")) return "info";
  return "muted";
}

/** The audit log (spec §36). */
export function AuditTable() {
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "created_at" });
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const query = useAuditLogs({
    page: list.page,
    page_size: list.pageSize,
    sort: list.sort,
    order: list.order,
    action: list.filter("action"),
    user_id: list.filter("user_id"),
    resource_type: list.filter("resource_type"),
    since: list.filter("since"),
    until: list.filter("until"),
  });

  // The audit log stores user ids; names come from the member list. Only
  // fetched when the caller may read members.
  const members = useMembers(can(PERM.USER_READ) ? { page: 1, page_size: 100 } : {});

  const memberName = useMemo(() => {
    const byUserId = new Map(
      (members.data?.items ?? []).map((member) => [
        member.user_id,
        userDisplayName(member.user),
      ]),
    );
    return (userId: string | null | undefined) => {
      if (!userId) return "System";
      return byUserId.get(userId) ?? `${userId.slice(0, 8)}…`;
    };
  }, [members.data]);

  const columns = useMemo<ColumnDef<AuditLog, unknown>[]>(
    () => [
      {
        accessorKey: "created_at",
        meta: { label: "Date" },
        enableHiding: false,
        header: () => <span className="text-xs font-medium">Date</span>,
        cell: ({ row }) => (
          <span className="tabular text-sm whitespace-nowrap">
            {formatDateTime(row.original.created_at)}
          </span>
        ),
      },
      {
        accessorKey: "user_id",
        meta: { label: "User" },
        header: () => <span className="text-xs font-medium">User</span>,
        cell: ({ row }) => (
          <span className="text-sm">{memberName(row.original.user_id)}</span>
        ),
      },
      {
        accessorKey: "action",
        meta: { label: "Action" },
        header: () => <span className="text-xs font-medium">Action</span>,
        cell: ({ row }) => (
          <Badge variant={actionTone(row.original.action)}>{row.original.action}</Badge>
        ),
      },
      {
        accessorKey: "resource_type",
        meta: { label: "Resource" },
        header: () => <span className="text-xs font-medium">Resource</span>,
        cell: ({ row }) => (
          <span className="text-sm">
            {row.original.resource_type ? humanizeEnum(row.original.resource_type) : "—"}
            {row.original.resource_id ? (
              <span className="text-muted-foreground ml-1 text-xs">
                {row.original.resource_id.slice(0, 8)}
              </span>
            ) : null}
          </span>
        ),
      },
      {
        accessorKey: "ip_address",
        meta: { label: "IP" },
        header: () => <span className="text-xs font-medium">IP</span>,
        cell: ({ row }) => (
          <span className="tabular text-muted-foreground text-sm">
            {row.original.ip_address ?? "—"}
          </span>
        ),
      },
      {
        id: "details",
        size: 88,
        enableHiding: false,
        header: () => <span className="sr-only">Details</span>,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={(event) => {
              event.stopPropagation();
              setSelected(row.original);
            }}
          >
            Details
          </Button>
        ),
      },
    ],
    [memberName],
  );

  const meta = query.data?.meta;

  return (
    <>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        isFetching={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        resourceLabel="the audit log"
        onRowClick={(row) => setSelected(row)}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        mobileRow={(row) => (
          <button
            type="button"
            onClick={() => setSelected(row)}
            className="w-full space-y-1 text-left"
          >
            <div className="flex items-start justify-between gap-2">
              <Badge variant={actionTone(row.action)}>{row.action}</Badge>
              <span className="text-muted-foreground text-xs">
                {formatDateTime(row.created_at)}
              </span>
            </div>
            <div className="text-muted-foreground text-xs">
              {memberName(row.user_id)}
              {row.resource_type ? ` · ${humanizeEnum(row.resource_type)}` : ""}
            </div>
          </button>
        )}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            activeFilterCount={list.activeFilterCount}
            onResetFilters={list.resetFilters}
            search={
              <SearchInput
                value={list.filter("action") ?? ""}
                onChange={(value) => list.setFilter("action", value || null)}
                placeholder="Filter by action…"
                className="w-full sm:w-56"
              />
            }
            filters={
              <>
                {can(PERM.USER_READ) ? (
                  <FilterDropdown
                    label="User"
                    options={(members.data?.items ?? []).map((member) => ({
                      value: member.user_id,
                      label: userDisplayName(member.user),
                    }))}
                    value={list.filter("user_id")}
                    onChange={(value) => list.setFilter("user_id", value)}
                  />
                ) : null}

                <DateRangePicker
                  from={list.filter("since")}
                  to={list.filter("until")}
                  onChange={({ from, to }) =>
                    list.setFilters({ since: from, until: to })
                  }
                />
              </>
            }
          />
        )}
        emptyState={
          <EmptyState
            icon={ScrollText}
            title={
              list.activeFilterCount > 0 ? "No events match these filters" : "No audit events"
            }
            description={
              list.activeFilterCount > 0
                ? "Try a wider date range or a different action."
                : "Security and business events are recorded here as your team works."
            }
            action={
              list.activeFilterCount > 0 ? (
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        }
        footer={() =>
          meta ? (
            <DataTablePagination
              meta={meta}
              onPageChange={list.setPage}
              onPageSizeChange={list.setPageSize}
            />
          ) : null
        }
      />

      {/*
        The event drawer renders the row we already hold: the backend exposes no
        `/audit-logs/{id}` endpoint, and `metadata` carries the structured
        context. Recorded in docs/API_CONTRACT.md under "Known gaps".
      */}
      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{selected?.action ?? "Audit event"}</SheetTitle>
            <SheetDescription>
              {selected ? formatDateTime(selected.created_at) : null}
            </SheetDescription>
          </SheetHeader>

          {selected ? (
            <div className="space-y-6 p-4">
              <DefinitionList
                items={[
                  { label: "Action", value: selected.action },
                  { label: "User", value: memberName(selected.user_id) },
                  {
                    label: "Resource",
                    value: selected.resource_type
                      ? humanizeEnum(selected.resource_type)
                      : null,
                  },
                  { label: "Resource ID", value: selected.resource_id },
                  { label: "IP address", value: selected.ip_address },
                  { label: "Request ID", value: selected.request_id },
                  {
                    label: "User agent",
                    value: selected.user_agent ? truncate(selected.user_agent, 48) : null,
                  },
                ]}
              />

              {selected.metadata && Object.keys(selected.metadata).length > 0 ? (
                <div>
                  <h3 className="mb-2 text-xs font-medium tracking-wide uppercase">
                    Event data
                  </h3>
                  <pre className="bg-muted/50 scrollbar-thin max-h-72 overflow-auto rounded-md p-3 text-xs">
                    {JSON.stringify(selected.metadata, null, 2)}
                  </pre>
                </div>
              ) : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </>
  );
}

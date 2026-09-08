"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Globe, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { PermissionGate } from "@/components/shared/permission-gate";
import { SearchInput } from "@/components/shared/search-input";
import { StatusBadge } from "@/components/shared/status-badge";
import { CLIENT_WEBSITE_STATUSES } from "@/config/enums";
import { CLIENT_WEBSITE_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import {
  useDeleteWebsite,
  useUpdateWebsite,
  useWebsites,
} from "@/features/websites/api/use-websites";
import { websiteColumns } from "@/features/websites/components/website-columns";
import { useListState } from "@/hooks/use-list-state";
import { errorMessage } from "@/lib/api/errors";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { displayDomain } from "@/lib/utils/format";
import type { ClientWebsite } from "@/types/api";

const FILTER_KEYS = ["status", "industry", "target_country"] as const;

/** The client-websites list (spec §19). */
export function WebsitesTable() {
  const router = useRouter();
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "created_at" });

  const [pendingArchive, setPendingArchive] = useState<ClientWebsite | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ClientWebsite | null>(null);

  const query = useWebsites({
    ...list.pageParams,
    status: list.filter("status"),
    industry: list.filter("industry"),
    target_country: list.filter("target_country"),
  });

  // Mutations are bound to the row the dialog is about; `useUpdateWebsite`
  // needs an id up front, so a stable empty string keeps the hook order fixed
  // while no dialog is open.
  const archiveWebsite = useUpdateWebsite(pendingArchive?.id ?? "");
  const deleteWebsite = useDeleteWebsite();

  const columns = useMemo(
    () =>
      websiteColumns({
        can,
        onArchive: setPendingArchive,
        onDelete: setPendingDelete,
      }),
    [can],
  );

  const items = query.data?.items ?? [];
  const meta = query.data?.meta;

  const hasFilters = list.activeFilterCount > 0;

  return (
    <>
      <DataTable
        columns={columns}
        data={items}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        isFetching={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        resourceLabel="your client websites"
        onRowClick={(row) => router.push(`/websites/${row.id}`)}
        mobileRow={(row) => (
          <div className="space-y-1">
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium">{row.name}</span>
              <StatusBadge status={row.status} labels={CLIENT_WEBSITE_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground text-xs">
              {displayDomain(row.website_url)}
            </div>
            <div className="text-muted-foreground text-xs">
              {row.industry ?? "No industry"} ·{" "}
              {row.target_country?.toUpperCase() ?? "No country"}
            </div>
          </div>
        )}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            activeFilterCount={list.activeFilterCount}
            onResetFilters={list.resetFilters}
            search={
              <SearchInput
                value={list.search}
                onChange={list.setSearch}
                placeholder="Search name or domain…"
                className="w-full sm:w-64"
              />
            }
            filters={
              <FilterDropdown
                label="Status"
                options={optionsFromEnum(
                  CLIENT_WEBSITE_STATUSES,
                  CLIENT_WEBSITE_STATUS_LABELS,
                )}
                value={list.filter("status")}
                onChange={(value) => list.setFilter("status", value)}
              />
            }
          />
        )}
        emptyState={
          hasFilters ? (
            <EmptyState
              icon={Globe}
              title="No websites match these filters"
              description="Try clearing the filters or searching for a different domain."
              action={
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Globe}
              title="No client websites yet"
              description="Add the site you want to promote. Campaigns and free listing opportunities are organised per website."
              action={
                <PermissionGate permission={PERM.CLIENT_WEBSITE_CREATE}>
                  <Button size="sm" onClick={() => router.push("/websites/new")}>
                    <Plus className="size-4" aria-hidden />
                    Add client website
                  </Button>
                </PermissionGate>
              }
            />
          )
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
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
      />

      <ConfirmDialog
        open={pendingArchive !== null}
        onOpenChange={(open) => !open && setPendingArchive(null)}
        title="Archive this website?"
        description={
          <>
            <strong>{pendingArchive?.name}</strong> will be hidden from the active list and
            excluded from new campaigns. Existing campaigns and submissions are kept.
          </>
        }
        confirmLabel="Archive"
        onConfirm={async () => {
          if (!pendingArchive) return;
          try {
            await archiveWebsite.mutateAsync({ status: "ARCHIVED" });
            toast.success("Website archived");
            setPendingArchive(null);
          } catch (error) {
            toast.error("Couldn't archive website", { description: errorMessage(error) });
            throw error;
          }
        }}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this website?"
        description={
          <>
            <strong>{pendingDelete?.name}</strong> will be deleted permanently. Its campaigns,
            opportunities and submissions may be removed with it. This cannot be undone.
          </>
        }
        confirmLabel="Delete website"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            await deleteWebsite.mutateAsync(pendingDelete.id);
            toast.success("Website deleted");
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't delete website", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}

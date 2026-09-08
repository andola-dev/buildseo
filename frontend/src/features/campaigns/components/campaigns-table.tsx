"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Megaphone, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { PermissionGate } from "@/components/shared/permission-gate";
import { SearchInput } from "@/components/shared/search-input";
import { StatusBadge } from "@/components/shared/status-badge";
import { CAMPAIGN_STATUSES } from "@/config/enums";
import { CAMPAIGN_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { campaignColumns } from "@/features/campaigns/components/campaign-columns";
import {
  useCampaigns,
  useDeleteCampaign,
} from "@/features/campaigns/api/use-campaigns";
import { useWebsiteOptions } from "@/features/websites/api/use-websites";
import { useListState } from "@/hooks/use-list-state";
import { campaignsApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useTenantId } from "@/lib/tenant/use-tenant";
import { queryKeys } from "@/lib/query/keys";
import { useQueryClient } from "@tanstack/react-query";
import { formatNumber } from "@/lib/utils/format";
import type { Campaign, CampaignStatus } from "@/types/api";

const FILTER_KEYS = ["status", "client_website_id", "target_country"] as const;

/** The campaigns list (spec §20). */
export function CampaignsTable() {
  const router = useRouter();
  const tenantId = useTenantId();
  const queryClient = useQueryClient();
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "created_at" });

  const [pendingDelete, setPendingDelete] = useState<Campaign | null>(null);

  const query = useCampaigns({
    ...list.pageParams,
    status: list.filter("status"),
    client_website_id: list.filter("client_website_id"),
    target_country: list.filter("target_country"),
  });

  const websites = useWebsiteOptions();
  const deleteCampaign = useDeleteCampaign();

  /** Resolve website ids to names; `CampaignRead` carries only the id. */
  const websiteName = useCallback(
    (websiteId: string) =>
      websites.data?.items.find((website) => website.id === websiteId)?.name ?? "—",
    [websites.data],
  );

  const handleStatusChange = useCallback(
    async (campaign: Campaign, status: CampaignStatus) => {
      if (!tenantId) return;
      try {
        await campaignsApi.updateCampaign(tenantId, campaign.id, { status });
        await queryClient.invalidateQueries({
          queryKey: queryKeys.campaigns.all(tenantId),
        });
        toast.success(`Campaign marked ${CAMPAIGN_STATUS_LABELS[status].toLowerCase()}`);
      } catch (error) {
        toast.error("Couldn't update campaign", { description: errorMessage(error) });
      }
    },
    [queryClient, tenantId],
  );

  const columns = useMemo(
    () =>
      campaignColumns({
        can,
        websiteName,
        onDelete: setPendingDelete,
        onStatusChange: (campaign, status) => void handleStatusChange(campaign, status),
      }),
    [can, websiteName, handleStatusChange],
  );

  const meta = query.data?.meta;
  const hasFilters = list.activeFilterCount > 0;

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
        resourceLabel="your campaigns"
        onRowClick={(row) => router.push(`/campaigns/${row.id}`)}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        mobileRow={(row) => (
          <div className="space-y-1">
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium">{row.name}</span>
              <StatusBadge status={row.status} labels={CAMPAIGN_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground text-xs">
              {websiteName(row.client_website_id)}
            </div>
            <div className="text-muted-foreground text-xs">
              {row.target_link_count
                ? `${formatNumber(row.target_link_count)} target links`
                : "No link target"}
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
                placeholder="Search campaigns…"
                className="w-full sm:w-64"
              />
            }
            filters={
              <>
                <FilterDropdown
                  label="Status"
                  options={optionsFromEnum(CAMPAIGN_STATUSES, CAMPAIGN_STATUS_LABELS)}
                  value={list.filter("status")}
                  onChange={(value) => list.setFilter("status", value)}
                />
                <FilterDropdown
                  label="Website"
                  options={(websites.data?.items ?? []).map((website) => ({
                    value: website.id,
                    label: website.name,
                  }))}
                  value={list.filter("client_website_id")}
                  onChange={(value) => list.setFilter("client_website_id", value)}
                />
              </>
            }
          />
        )}
        emptyState={
          hasFilters ? (
            <EmptyState
              icon={Megaphone}
              title="No campaigns match these filters"
              description="Try a different status, or clear the filters to see everything."
              action={
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Megaphone}
              title="No campaigns yet"
              description="Create your first campaign to start discovering free listing opportunities."
              action={
                <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
                  <Button size="sm" onClick={() => router.push("/campaigns/new")}>
                    <Plus className="size-4" aria-hidden />
                    Create campaign
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
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this campaign?"
        description={
          <>
            <strong>{pendingDelete?.name}</strong> will be deleted permanently, along with its
            opportunities and submissions. This cannot be undone.
          </>
        }
        confirmLabel="Delete campaign"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            await deleteCampaign.mutateAsync(pendingDelete.id);
            toast.success("Campaign deleted");
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't delete campaign", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}

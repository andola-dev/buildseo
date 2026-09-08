"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Link2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { SearchInput } from "@/components/shared/search-input";
import { ScoreBadge } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { OPPORTUNITY_STATUSES, OPPORTUNITY_TYPES } from "@/config/enums";
import { OPPORTUNITY_STATUS_LABELS, OPPORTUNITY_TYPE_LABELS } from "@/config/labels";
import { useCampaignOptions } from "@/features/campaigns/api/use-campaigns";
import { useOpportunities } from "@/features/opportunities/api/use-opportunities";
import { opportunityColumns } from "@/features/opportunities/components/opportunity-columns";
import { RejectDialog } from "@/features/opportunities/components/reject-dialog";
import { useListState } from "@/hooks/use-list-state";
import { opportunitiesApi, submissionsApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useTenantId } from "@/lib/tenant/use-tenant";
import { queryKeys } from "@/lib/query/keys";
import { useQueryClient } from "@tanstack/react-query";
import { displayDomain } from "@/lib/utils/format";
import type { Opportunity } from "@/types/api";

const FILTER_KEYS = [
  "status",
  "campaign_id",
  "opportunity_type",
  "category",
  "min_priority",
  "min_score",
] as const;

/** The opportunities workflow table (spec §25). */
export function OpportunitiesTable() {
  const router = useRouter();
  const tenantId = useTenantId();
  const queryClient = useQueryClient();
  const { can } = usePermissions();
  const list = useListState({
    filterKeys: FILTER_KEYS,
    defaultSort: "qualification_score",
  });

  const [rejecting, setRejecting] = useState<Opportunity | null>(null);
  const [busy, setBusy] = useState(false);

  const minScore = list.filter("min_score");
  const minPriority = list.filter("min_priority");

  const query = useOpportunities({
    ...list.pageParams,
    status: list.filter("status"),
    campaign_id: list.filter("campaign_id"),
    opportunity_type: list.filter("opportunity_type"),
    category: list.filter("category"),
    min_score: minScore ? Number.parseFloat(minScore) : null,
    min_priority: minPriority ? Number.parseInt(minPriority, 10) : null,
  });

  const campaigns = useCampaignOptions();

  const campaignName = useCallback(
    (campaignId: string) =>
      campaigns.data?.items.find((campaign) => campaign.id === campaignId)?.name ?? "—",
    [campaigns.data],
  );

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.opportunities.all(tenantId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
  }, [queryClient, tenantId]);

  const handleSelect = useCallback(
    async (opportunity: Opportunity) => {
      if (!tenantId) return;
      setBusy(true);
      try {
        await opportunitiesApi.selectOpportunity(tenantId, opportunity.id);
        await refresh();
        toast.success("Opportunity approved", {
          description: "It's now ready to prepare a submission.",
        });
      } catch (error) {
        toast.error("Couldn't approve opportunity", { description: errorMessage(error) });
      } finally {
        setBusy(false);
      }
    },
    [refresh, tenantId],
  );

  /**
   * Prepare a submission from an approved opportunity.
   *
   * `use_approved_content` tells the backend to copy the reviewed listing copy
   * into the submission, so an approved draft isn't retyped.
   */
  const handlePrepare = useCallback(
    async (opportunity: Opportunity) => {
      if (!tenantId) return;
      setBusy(true);
      try {
        const submission = await submissionsApi.createSubmission(tenantId, {
          opportunity_id: opportunity.id,
          use_approved_content: true,
        });
        await refresh();
        await queryClient.invalidateQueries({
          queryKey: queryKeys.submissions.all(tenantId),
        });
        toast.success("Submission prepared", { description: "Review it before approving." });
        router.push(`/submissions/${submission.id}`);
      } catch (error) {
        toast.error("Couldn't prepare submission", { description: errorMessage(error) });
      } finally {
        setBusy(false);
      }
    },
    [queryClient, refresh, router, tenantId],
  );

  const columns = useMemo(
    () =>
      opportunityColumns({
        can,
        campaignName,
        onSelect: (opportunity) => void handleSelect(opportunity),
        onReject: setRejecting,
        onPrepare: (opportunity) => void handlePrepare(opportunity),
      }),
    [can, campaignName, handleSelect, handlePrepare],
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
        isFetching={(query.isFetching && !query.isPending) || busy}
        error={query.error}
        onRetry={() => void query.refetch()}
        resourceLabel="your opportunities"
        onRowClick={(row) => router.push(`/opportunities/${row.id}`)}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        mobileRow={(row) => (
          <div className="space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <span className="min-w-0 truncate font-medium">
                {row.suggested_title ?? "Untitled listing"}
              </span>
              <StatusBadge status={row.status} labels={OPPORTUNITY_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {campaignName(row.campaign_id)} · {displayDomain(row.target_url)}
            </div>
            <div className="text-muted-foreground text-xs">
              Score <ScoreBadge score={row.qualification_score} kind="opportunity" />
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
                placeholder="Search opportunities…"
                className="w-full sm:w-64"
              />
            }
            filters={
              <>
                <FilterDropdown
                  label="Campaign"
                  options={(campaigns.data?.items ?? []).map((campaign) => ({
                    value: campaign.id,
                    label: campaign.name,
                  }))}
                  value={list.filter("campaign_id")}
                  onChange={(value) => list.setFilter("campaign_id", value)}
                />
                <FilterDropdown
                  label="Status"
                  options={optionsFromEnum(
                    OPPORTUNITY_STATUSES,
                    OPPORTUNITY_STATUS_LABELS,
                  )}
                  value={list.filter("status")}
                  onChange={(value) => list.setFilter("status", value)}
                />
                <FilterDropdown
                  label="Type"
                  options={optionsFromEnum(OPPORTUNITY_TYPES, OPPORTUNITY_TYPE_LABELS)}
                  value={list.filter("opportunity_type")}
                  onChange={(value) => list.setFilter("opportunity_type", value)}
                />
                <FilterDropdown
                  label="Min score"
                  options={[
                    { value: "40", label: "40+" },
                    { value: "60", label: "60+" },
                    { value: "70", label: "70+" },
                    { value: "80", label: "80+" },
                  ]}
                  value={minScore}
                  onChange={(value) => list.setFilter("min_score", value)}
                />
              </>
            }
          />
        )}
        emptyState={
          hasFilters ? (
            <EmptyState
              icon={Link2}
              title="No opportunities match these filters"
              description="Try a lower score threshold, or clear the filters."
              action={
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Link2}
              title="No opportunities yet"
              description="Opportunities are created when qualified publishers are matched to a campaign. Run discovery to get started."
              action={
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push("/publishers/discovery")}
                >
                  Go to discovery
                </Button>
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

      <RejectDialog
        open={rejecting !== null}
        onOpenChange={(open) => !open && setRejecting(null)}
        title="Reject this opportunity?"
        description="It won't be submitted. The reason is recorded for whoever reviews this campaign next."
        submitting={busy}
        onConfirm={async (reason) => {
          if (!tenantId || !rejecting) return;
          setBusy(true);
          try {
            await opportunitiesApi.rejectOpportunity(tenantId, rejecting.id, { reason });
            await refresh();
            toast.success("Opportunity rejected");
            setRejecting(null);
          } catch (error) {
            toast.error("Couldn't reject opportunity", { description: errorMessage(error) });
          } finally {
            setBusy(false);
          }
        }}
      />
    </>
  );
}

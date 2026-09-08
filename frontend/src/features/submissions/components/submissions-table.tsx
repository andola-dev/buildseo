"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { SearchInput } from "@/components/shared/search-input";
import { StatusBadge } from "@/components/shared/status-badge";
import { SUBMISSION_METHODS } from "@/config/enums";
import { SUBMISSION_METHOD_LABELS, SUBMISSION_STATUS_LABELS } from "@/config/labels";
import { useCampaignOptions } from "@/features/campaigns/api/use-campaigns";
import { useSubmissions } from "@/features/submissions/api/use-submissions";
import { submissionColumns } from "@/features/submissions/components/submission-columns";
import { RejectDialog } from "@/features/opportunities/components/reject-dialog";
import { useListState } from "@/hooks/use-list-state";
import { submissionsApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useTenantId } from "@/lib/tenant/use-tenant";
import { queryKeys } from "@/lib/query/keys";
import { useQueryClient } from "@tanstack/react-query";
import { displayDomain } from "@/lib/utils/format";
import type { Submission } from "@/types/api";

const FILTER_KEYS = ["status", "campaign_id", "submission_method"] as const;

/**
 * Status tabs (spec §28).
 *
 * Tabs are just URL state on the same route, so a tab is bookmarkable and the
 * sidebar's "Pending Review" entry lands on exactly this view.
 */
const TABS = [
  { value: "all", label: "All", status: null },
  { value: "PENDING_APPROVAL", label: "Pending Review", status: "PENDING_APPROVAL" },
  { value: "READY", label: "Ready", status: "READY" },
  { value: "SUBMITTED", label: "Submitted", status: "SUBMITTED" },
  { value: "PUBLISHED", label: "Published", status: "PUBLISHED" },
  { value: "VERIFIED", label: "Verified", status: "VERIFIED" },
  { value: "FAILED", label: "Failed", status: "FAILED" },
] as const;

export function SubmissionsTable() {
  const router = useRouter();
  const tenantId = useTenantId();
  const queryClient = useQueryClient();
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "created_at" });

  const [rejecting, setRejecting] = useState<Submission | null>(null);
  const [busy, setBusy] = useState(false);

  const status = list.filter("status");

  const query = useSubmissions({
    ...list.pageParams,
    status,
    campaign_id: list.filter("campaign_id"),
    submission_method: list.filter("submission_method"),
  });

  const campaigns = useCampaignOptions();

  const campaignName = useCallback(
    (campaignId: string) =>
      campaigns.data?.items.find((campaign) => campaign.id === campaignId)?.name ?? "—",
    [campaigns.data],
  );

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all(tenantId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
  }, [queryClient, tenantId]);

  const handleApprove = useCallback(
    async (submission: Submission) => {
      if (!tenantId) return;
      setBusy(true);
      try {
        await submissionsApi.approveSubmission(tenantId, submission.id, {});
        await refresh();
        toast.success("Submission approved");
      } catch (error) {
        toast.error("Couldn't approve submission", { description: errorMessage(error) });
      } finally {
        setBusy(false);
      }
    },
    [refresh, tenantId],
  );

  const handleVerify = useCallback(
    async (submission: Submission) => {
      if (!tenantId) return;
      setBusy(true);
      try {
        const updated = await submissionsApi.verifySubmission(tenantId, submission.id, {
          fetch_live: true,
        });
        await refresh();
        toast.success("Verification complete", {
          description: `Status is now ${SUBMISSION_STATUS_LABELS[updated.status as keyof typeof SUBMISSION_STATUS_LABELS] ?? updated.status}.`,
        });
      } catch (error) {
        toast.error("Couldn't verify link", { description: errorMessage(error) });
      } finally {
        setBusy(false);
      }
    },
    [refresh, tenantId],
  );

  const columns = useMemo(
    () =>
      submissionColumns({
        can,
        campaignName,
        onApprove: (submission) => void handleApprove(submission),
        onVerify: (submission) => void handleVerify(submission),
        onReject: setRejecting,
      }),
    [can, campaignName, handleApprove, handleVerify],
  );

  const meta = query.data?.meta;
  const activeTab = TABS.find((tab) => tab.status === status)?.value ?? "all";

  return (
    <>
      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          const tab = TABS.find((entry) => entry.value === value);
          list.setFilter("status", tab?.status ?? null);
        }}
        className="mb-4"
      >
        <TabsList className="h-auto flex-wrap justify-start">
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        isFetching={(query.isFetching && !query.isPending) || busy}
        error={query.error}
        onRetry={() => void query.refetch()}
        resourceLabel="your submissions"
        onRowClick={(row) => router.push(`/submissions/${row.id}`)}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        mobileRow={(row) => (
          <div className="space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <span className="min-w-0 truncate font-medium">
                {row.submitted_title ?? "Untitled submission"}
              </span>
              <StatusBadge status={row.status} labels={SUBMISSION_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {campaignName(row.campaign_id)} · {displayDomain(row.target_url)}
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
                placeholder="Search submissions…"
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
                  label="Method"
                  options={optionsFromEnum(SUBMISSION_METHODS, SUBMISSION_METHOD_LABELS)}
                  value={list.filter("submission_method")}
                  onChange={(value) => list.setFilter("submission_method", value)}
                />
              </>
            }
          />
        )}
        emptyState={
          <EmptyState
            icon={Send}
            title={status ? "Nothing in this view" : "No submissions yet"}
            description={
              status
                ? "No submissions currently have this status."
                : "Approve an opportunity and prepare a submission to start building links."
            }
            action={
              status ? (
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Show all submissions
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push("/opportunities?status=QUALIFIED")}
                >
                  Review opportunities
                </Button>
              )
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

      <RejectDialog
        open={rejecting !== null}
        onOpenChange={(open) => !open && setRejecting(null)}
        title="Reject this submission?"
        description="It won't be submitted to the publisher. The reason is recorded in the audit trail."
        submitting={busy}
        onConfirm={async (reason) => {
          if (!tenantId || !rejecting) return;
          setBusy(true);
          try {
            await submissionsApi.transitionSubmission(tenantId, rejecting.id, {
              target_status: "REJECTED",
              reason,
            });
            await refresh();
            toast.success("Submission rejected");
            setRejecting(null);
          } catch (error) {
            toast.error("Couldn't reject submission", { description: errorMessage(error) });
          } finally {
            setBusy(false);
          }
        }}
      />
    </>
  );
}

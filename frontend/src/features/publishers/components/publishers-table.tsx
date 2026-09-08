"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Globe, Search } from "lucide-react";
import { toast } from "sonner";
import type { RowSelectionState } from "@tanstack/react-table";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { PermissionGate } from "@/components/shared/permission-gate";
import { SearchInput } from "@/components/shared/search-input";
import { ScoreBadge } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  PUBLISHER_CATEGORIES,
  PUBLISHER_STATUSES,
  SUBMISSION_METHODS,
} from "@/config/enums";
import {
  PUBLISHER_CATEGORY_LABELS,
  PUBLISHER_STATUS_LABELS,
  SUBMISSION_METHOD_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import {
  useDeletePublisher,
  usePublishers,
} from "@/features/publishers/api/use-publishers";
import { publisherColumns } from "@/features/publishers/components/publisher-columns";
import { useListState } from "@/hooks/use-list-state";
import { publishersApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useTenantId } from "@/lib/tenant/use-tenant";
import { queryKeys } from "@/lib/query/keys";
import { useQueryClient } from "@tanstack/react-query";
import { displayDomain } from "@/lib/utils/format";
import type { Publisher } from "@/types/api";

const FILTER_KEYS = [
  "status",
  "category",
  "country",
  "language",
  "submission_method",
  "min_quality_score",
  "max_spam_score",
] as const;

/** Numeric score thresholds, which don't fit a select. */
function ScoreFilters({
  minQuality,
  maxSpam,
  onChange,
}: {
  minQuality: string | null;
  maxSpam: string | null;
  onChange: (patch: Record<string, string | null>) => void;
}) {
  const active = [minQuality, maxSpam].filter(Boolean).length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 font-normal">
          <span className="text-muted-foreground">Scores</span>
          <span>{active > 0 ? `${active} set` : "Any"}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="filter-min-quality">Minimum quality score</Label>
          <Input
            id="filter-min-quality"
            type="number"
            min={0}
            max={100}
            value={minQuality ?? ""}
            onChange={(event) =>
              onChange({ min_quality_score: event.target.value || null })
            }
            placeholder="0–100"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="filter-max-spam">Maximum spam score</Label>
          <Input
            id="filter-max-spam"
            type="number"
            min={0}
            max={100}
            value={maxSpam ?? ""}
            onChange={(event) => onChange({ max_spam_score: event.target.value || null })}
            placeholder="0–100"
          />
        </div>

        {active > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={() => onChange({ min_quality_score: null, max_spam_score: null })}
          >
            Clear score filters
          </Button>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

/**
 * The publisher database (spec §22).
 *
 * Free listings only: the API module pins `pricing_type=FREE`, so paid
 * inventory is never fetched and no filter can surface it (spec §73).
 */
export function PublishersTable() {
  const router = useRouter();
  const tenantId = useTenantId();
  const queryClient = useQueryClient();
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "quality_score" });

  const [selection, setSelection] = useState<RowSelectionState>({});
  const [pendingDelete, setPendingDelete] = useState<Publisher | null>(null);
  const [qualifying, setQualifying] = useState(false);

  const minQuality = list.filter("min_quality_score");
  const maxSpam = list.filter("max_spam_score");

  const query = usePublishers({
    ...list.pageParams,
    status: list.filter("status"),
    category: list.filter("category"),
    country: list.filter("country"),
    language: list.filter("language"),
    submission_method: list.filter("submission_method"),
    min_quality_score: minQuality ? Number.parseFloat(minQuality) : null,
    max_spam_score: maxSpam ? Number.parseFloat(maxSpam) : null,
  });

  const deletePublisher = useDeletePublisher();

  async function qualifyOne(publisher: Publisher) {
    if (!tenantId) return;
    setQualifying(true);
    try {
      const result = await publishersApi.qualifyPublisher(tenantId, publisher.id, {
        fetch_live: true,
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
      toast.success("Publisher re-qualified", {
        description: `Quality ${Math.round(result.scores.quality_score)} · recommended ${result.scores.recommended_status}`,
      });
    } catch (error) {
      toast.error("Couldn't qualify publisher", { description: errorMessage(error) });
    } finally {
      setQualifying(false);
    }
  }

  /**
   * Bulk re-qualification.
   *
   * Sequential rather than parallel: each call may trigger a live crawl on the
   * backend, and firing 100 at once would be a burst the rate limiter should
   * not have to absorb.
   */
  async function qualifySelected(publishers: Publisher[]) {
    if (!tenantId || publishers.length === 0) return;
    setQualifying(true);

    let succeeded = 0;
    let failed = 0;

    for (const publisher of publishers) {
      try {
        await publishersApi.qualifyPublisher(tenantId, publisher.id, { fetch_live: false });
        succeeded += 1;
      } catch {
        failed += 1;
      }
    }

    await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    setSelection({});
    setQualifying(false);

    if (failed === 0) {
      toast.success(`Re-qualified ${succeeded} publisher${succeeded === 1 ? "" : "s"}`);
    } else {
      toast.warning(`Re-qualified ${succeeded}, ${failed} failed`, {
        description: "Open a publisher to see why it couldn't be scored.",
      });
    }
  }

  const columns = useMemo(
    () =>
      publisherColumns({
        can,
        onDelete: setPendingDelete,
        onQualify: (publisher) => void qualifyOne(publisher),
      }),
    // `qualifyOne` closes over `tenantId` and the query client, both stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [can, tenantId],
  );

  const items = query.data?.items ?? [];
  const meta = query.data?.meta;
  const selectedRows = items.filter((item) => selection[item.id]);
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
        resourceLabel="your publishers"
        onRowClick={(row) => router.push(`/publishers/${row.id}`)}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        rowSelection={selection}
        onRowSelectionChange={setSelection}
        mobileRow={(row) => (
          <div className="space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <span className="min-w-0 truncate font-medium">
                {row.name ?? displayDomain(row.domain)}
              </span>
              <StatusBadge status={row.status} labels={PUBLISHER_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {displayDomain(row.domain)}
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-muted-foreground">
                Quality <ScoreBadge score={row.quality_score} kind="quality" />
              </span>
              <span className="text-muted-foreground">
                Spam <ScoreBadge score={row.spam_score} kind="spam" />
              </span>
            </div>
          </div>
        )}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            activeFilterCount={list.activeFilterCount}
            onResetFilters={() => {
              list.resetFilters();
              setSelection({});
            }}
            search={
              <SearchInput
                value={list.search}
                onChange={list.setSearch}
                placeholder="Search publisher or domain…"
                className="w-full sm:w-72"
              />
            }
            filters={
              <>
                <FilterDropdown
                  label="Status"
                  options={optionsFromEnum(PUBLISHER_STATUSES, PUBLISHER_STATUS_LABELS)}
                  value={list.filter("status")}
                  onChange={(value) => list.setFilter("status", value)}
                />
                <FilterDropdown
                  label="Category"
                  options={optionsFromEnum(
                    PUBLISHER_CATEGORIES,
                    PUBLISHER_CATEGORY_LABELS,
                  )}
                  value={list.filter("category")}
                  onChange={(value) => list.setFilter("category", value)}
                />
                <FilterDropdown
                  label="Submission"
                  options={optionsFromEnum(SUBMISSION_METHODS, SUBMISSION_METHOD_LABELS)}
                  value={list.filter("submission_method")}
                  onChange={(value) => list.setFilter("submission_method", value)}
                />
                <ScoreFilters
                  minQuality={minQuality}
                  maxSpam={maxSpam}
                  onChange={list.setFilters}
                />
              </>
            }
            selectionActions={
              <PermissionGate permission={PERM.PUBLISHER_QUALIFY}>
                <Button
                  variant="outline"
                  size="sm"
                  loading={qualifying}
                  onClick={() => void qualifySelected(selectedRows)}
                >
                  Re-qualify {selectedRows.length}
                </Button>
              </PermissionGate>
            }
          />
        )}
        emptyState={
          hasFilters ? (
            <EmptyState
              icon={Globe}
              title="No publishers match these filters"
              description="Loosen the score thresholds, or clear the filters to see the whole database."
              action={
                <Button variant="outline" size="sm" onClick={list.resetFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Globe}
              title="No publishers yet"
              description="Run discovery to find free directories and listing sites that match your client's industry and market."
              action={
                <PermissionGate permission={PERM.PUBLISHER_DISCOVER}>
                  <Button size="sm" onClick={() => router.push("/publishers/discovery")}>
                    <Search className="size-4" aria-hidden />
                    Start discovery
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
              {...(selectedRows.length > 0
                ? {
                    selectionLabel: `${selectedRows.length} of ${items.length} on this page selected`,
                  }
                : {})}
            />
          ) : null
        }
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this publisher?"
        description={
          <>
            <strong>{pendingDelete?.name ?? pendingDelete?.domain}</strong> will be removed
            from the publisher database. Opportunities and submissions that reference it may
            be removed too. This cannot be undone.
          </>
        }
        confirmLabel="Delete publisher"
        destructive
        onConfirm={async () => {
          if (!pendingDelete) return;
          try {
            await deletePublisher.mutateAsync(pendingDelete.id);
            toast.success("Publisher deleted");
            setPendingDelete(null);
          } catch (error) {
            toast.error("Couldn't delete publisher", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}

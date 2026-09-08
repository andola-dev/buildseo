"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import {
  auditApi,
  campaignsApi,
  opportunitiesApi,
  publishersApi,
  submissionsApi,
} from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";

/**
 * The dashboard.
 *
 * The backend exposes no `/dashboard/summary` endpoint (see
 * `docs/API_CONTRACT.md`, "Known gaps"), so the KPI figures are composed from
 * the counters the real list endpoints already return: each query asks for
 * `page_size: 1` and reads `meta.total`, which is one cheap request per figure
 * rather than pulling rows the dashboard would then have to count itself.
 *
 * If a `/dashboard/summary` endpoint is added later, this hook is the only
 * thing that changes.
 */
export interface DashboardSummary {
  activeCampaigns: number;
  qualifiedPublishers: number;
  availableOpportunities: number;
  linksSubmitted: number;
  linksPublished: number;
  linksVerified: number;
  pendingReview: number;
}

export function useDashboardSummary() {
  const tenantId = useTenantId();
  const enabled = Boolean(tenantId);
  const one = { page: 1, page_size: 1 } as const;

  const results = useQueries({
    queries: [
      {
        queryKey: queryKeys.campaigns.list(tenantId, { ...one, status: "ACTIVE", count: true }),
        queryFn: () => campaignsApi.listCampaigns(tenantId!, { ...one, status: "ACTIVE" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.publishers.list(tenantId, {
          ...one,
          status: "QUALIFIED",
          count: true,
        }),
        queryFn: () => publishersApi.listPublishers(tenantId!, { ...one, status: "QUALIFIED" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.opportunities.list(tenantId, {
          ...one,
          status: "QUALIFIED",
          count: true,
        }),
        queryFn: () =>
          opportunitiesApi.listOpportunities(tenantId!, { ...one, status: "QUALIFIED" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.submissions.list(tenantId, {
          ...one,
          status: "SUBMITTED",
          count: true,
        }),
        queryFn: () =>
          submissionsApi.listSubmissions(tenantId!, { ...one, status: "SUBMITTED" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.submissions.list(tenantId, {
          ...one,
          status: "PUBLISHED",
          count: true,
        }),
        queryFn: () =>
          submissionsApi.listSubmissions(tenantId!, { ...one, status: "PUBLISHED" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.submissions.list(tenantId, {
          ...one,
          status: "VERIFIED",
          count: true,
        }),
        queryFn: () =>
          submissionsApi.listSubmissions(tenantId!, { ...one, status: "VERIFIED" }),
        enabled,
        staleTime: 60_000,
      },
      {
        queryKey: queryKeys.submissions.list(tenantId, {
          ...one,
          status: "PENDING_APPROVAL",
          count: true,
        }),
        queryFn: () =>
          submissionsApi.listSubmissions(tenantId!, { ...one, status: "PENDING_APPROVAL" }),
        enabled,
        staleTime: 60_000,
      },
    ],
  });

  const isPending = results.some((result) => result.isPending);
  // Only a total failure is worth an error state: a single missing counter
  // should not hide the rest of the dashboard.
  const error = results.every((result) => result.isError) ? results[0]?.error : null;

  const summary: DashboardSummary = {
    activeCampaigns: results[0]?.data?.meta.total ?? 0,
    qualifiedPublishers: results[1]?.data?.meta.total ?? 0,
    availableOpportunities: results[2]?.data?.meta.total ?? 0,
    linksSubmitted: results[3]?.data?.meta.total ?? 0,
    linksPublished: results[4]?.data?.meta.total ?? 0,
    linksVerified: results[5]?.data?.meta.total ?? 0,
    pendingReview: results[6]?.data?.meta.total ?? 0,
  };

  return {
    summary,
    isPending,
    error,
    refetch: () => Promise.all(results.map((result) => result.refetch())),
  };
}

/**
 * Recent activity.
 *
 * Built from the audit trail, which is the only endpoint that records what
 * happened and when. Requires `audit.read`; the caller hides the section when
 * the user lacks it.
 */
export function useRecentActivity(enabled: boolean) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.audit.list(tenantId, { recent: true }),
    queryFn: () =>
      auditApi.listAuditLogs(tenantId!, {
        page: 1,
        page_size: 12,
        sort: "created_at",
        order: "desc",
      }),
    enabled: Boolean(tenantId) && enabled,
    staleTime: 30_000,
  });
}

/** Campaigns with progress, for the dashboard's progress section. */
export function useCampaignProgress() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.campaigns.list(tenantId, { progress: true }),
    queryFn: () =>
      campaignsApi.listCampaigns(tenantId!, {
        page: 1,
        page_size: 5,
        status: "ACTIVE",
        sort: "created_at",
        order: "desc",
      }),
    enabled: Boolean(tenantId),
    staleTime: 60_000,
  });
}

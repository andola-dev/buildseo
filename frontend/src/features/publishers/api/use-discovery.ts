"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { IN_FLIGHT_STATUSES } from "@/config/enums";
import { publishersApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type { DiscoveryRequest, DiscoveryRunListParams } from "@/types/api";

/** Providers this workspace can use — some need a credential configured. */
export function useDiscoveryProviders() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.publishers.discoveryProviders(tenantId),
    queryFn: () => publishersApi.listDiscoveryProviders(tenantId!),
    enabled: Boolean(tenantId),
    staleTime: 5 * 60_000,
  });
}

/**
 * Discovery runs, polled while any run is still working.
 *
 * Discovery crawls the web and can take minutes, so it runs as a background job
 * and the UI observes it (spec §24). `refetchInterval` returns `false` once
 * every run has finished, so polling stops on its own rather than running for
 * as long as the page is open.
 */
export function useDiscoveryRuns(params: DiscoveryRunListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.publishers.discoveryRuns(tenantId, params),
    queryFn: () => publishersApi.listDiscoveryRuns(tenantId!, params),
    enabled: Boolean(tenantId),
    refetchInterval: (query) => {
      const runs = query.state.data?.items ?? [];
      const active = runs.some((run) => IN_FLIGHT_STATUSES.includes(run.status));
      return active ? 3000 : false;
    },
  });
}

/**
 * Start discovery.
 *
 * `run_async` is requested so the browser is never blocked waiting on a crawl.
 * The backend may still answer synchronously for a cheap provider, which
 * `startDiscovery` reports through its discriminated result.
 */
export function useStartDiscovery() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: DiscoveryRequest) =>
      publishersApi.startDiscovery(tenantId!, { ...payload, run_async: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    },
  });
}

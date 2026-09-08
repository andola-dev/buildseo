"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { websitesApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type {
  ClientWebsiteCreate,
  ClientWebsiteListParams,
  ClientWebsiteUpdate,
} from "@/types/api";

/**
 * Client websites.
 *
 * Every query is keyed by workspace and disabled until one is active, so no
 * request is made that the backend would reject with `TENANT_CONTEXT_REQUIRED`,
 * and no workspace can read another's cache (spec §16/§49).
 */
export function useWebsites(params: ClientWebsiteListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.websites.list(tenantId, params),
    queryFn: ({ signal }) => websitesApi.listWebsites(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

export function useWebsite(websiteId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.websites.detail(tenantId, websiteId ?? ""),
    queryFn: () => websitesApi.getWebsite(tenantId!, websiteId!),
    enabled: Boolean(tenantId && websiteId),
  });
}

/**
 * Every website in the workspace, for the campaign wizard's picker.
 *
 * A large page size is requested rather than paging, because a picker with
 * pagination is worse than one list; workspaces hold tens of client sites, not
 * thousands.
 */
export function useWebsiteOptions() {
  const tenantId = useTenantId();
  const params: ClientWebsiteListParams = { page_size: 100, status: "ACTIVE" };

  return useQuery({
    queryKey: queryKeys.websites.list(tenantId, { ...params, purpose: "options" }),
    queryFn: () => websitesApi.listWebsites(tenantId!, params),
    enabled: Boolean(tenantId),
    staleTime: 5 * 60_000,
  });
}

export function useCreateWebsite() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ClientWebsiteCreate) =>
      websitesApi.createWebsite(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.websites.all(tenantId) });
    },
  });
}

export function useUpdateWebsite(websiteId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ClientWebsiteUpdate) =>
      websitesApi.updateWebsite(tenantId!, websiteId, payload),
    onSuccess: async () => {
      // Invalidate the whole resource: a status change moves the row between
      // filtered views, so refreshing only the detail entry would leave a
      // stale list behind.
      await queryClient.invalidateQueries({ queryKey: queryKeys.websites.all(tenantId) });
    },
  });
}

export function useDeleteWebsite() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (websiteId: string) => websitesApi.deleteWebsite(tenantId!, websiteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.websites.all(tenantId) });
      // Campaigns reference a website, so their lists may now be stale too.
      await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
    },
  });
}

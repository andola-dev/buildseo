"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { campaignsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type { CampaignCreate, CampaignListParams, CampaignUpdate } from "@/types/api";

export function useCampaigns(params: CampaignListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.campaigns.list(tenantId, params),
    queryFn: ({ signal }) => campaignsApi.listCampaigns(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

export function useCampaign(campaignId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.campaigns.detail(tenantId, campaignId ?? ""),
    queryFn: () => campaignsApi.getCampaign(tenantId!, campaignId!),
    enabled: Boolean(tenantId && campaignId),
  });
}

/** Funnel counters for one campaign: discovered → qualified → published. */
export function useCampaignStats(campaignId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.campaigns.stats(tenantId, campaignId ?? ""),
    queryFn: () => campaignsApi.getCampaignStats(tenantId!, campaignId!),
    enabled: Boolean(tenantId && campaignId),
  });
}

/** Campaigns for a picker (opportunity filters, discovery target). */
export function useCampaignOptions() {
  const tenantId = useTenantId();
  const params: CampaignListParams = { page_size: 100, sort: "created_at", order: "desc" };

  return useQuery({
    queryKey: queryKeys.campaigns.list(tenantId, { ...params, purpose: "options" }),
    queryFn: () => campaignsApi.listCampaigns(tenantId!, params),
    enabled: Boolean(tenantId),
    staleTime: 5 * 60_000,
  });
}

export function useCreateCampaign() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CampaignCreate) => campaignsApi.createCampaign(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
      // A campaign belongs to a website, whose detail page lists them.
      await queryClient.invalidateQueries({ queryKey: queryKeys.websites.all(tenantId) });
    },
  });
}

export function useUpdateCampaign(campaignId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CampaignUpdate) =>
      campaignsApi.updateCampaign(tenantId!, campaignId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
    },
  });
}

export function useDeleteCampaign() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (campaignId: string) => campaignsApi.deleteCampaign(tenantId!, campaignId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
      // Opportunities and submissions are scoped to a campaign.
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(tenantId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all(tenantId) });
    },
  });
}

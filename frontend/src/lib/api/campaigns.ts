/** Free-listing campaigns for a client website. */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  Campaign,
  CampaignCreate,
  CampaignListParams,
  CampaignStats,
  CampaignUpdate,
  PaginatedEnvelope,
  UUID,
} from "@/types/api";

const BASE = "/campaigns";

export async function listCampaigns(
  tenantId: string,
  params?: CampaignListParams,
  signal?: AbortSignal,
): Promise<Page<Campaign>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Campaign>>(BASE, {
      query: { ...params },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

export async function getCampaign(tenantId: string, campaignId: UUID): Promise<Campaign> {
  return unwrap(await api.get<ApiEnvelope<Campaign>>(`${BASE}/${campaignId}`, { tenantId }));
}

export async function getCampaignStats(
  tenantId: string,
  campaignId: UUID,
): Promise<CampaignStats> {
  return unwrap(
    await api.get<ApiEnvelope<CampaignStats>>(`${BASE}/${campaignId}/stats`, { tenantId }),
  );
}

export async function createCampaign(
  tenantId: string,
  payload: CampaignCreate,
): Promise<Campaign> {
  return unwrap(await api.post<ApiEnvelope<Campaign>>(BASE, payload, { tenantId }));
}

export async function updateCampaign(
  tenantId: string,
  campaignId: UUID,
  payload: CampaignUpdate,
): Promise<Campaign> {
  return unwrap(
    await api.patch<ApiEnvelope<Campaign>>(`${BASE}/${campaignId}`, payload, { tenantId }),
  );
}

export async function deleteCampaign(tenantId: string, campaignId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${campaignId}`, { tenantId }));
}

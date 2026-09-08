/**
 * Per-workspace AI provider configuration and usage accounting.
 *
 * A config binds a purpose (content generation, discovery, …) to a provider,
 * model and stored credential. The key itself lives in `credentials`; this
 * resource only references it by id.
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  AiConfig,
  AiConfigUpsert,
  AiUsage,
  AiUsageListParams,
  AiUsageSummary,
  ApiEnvelope,
  PaginatedEnvelope,
  UUID,
} from "@/types/api";

export async function listAiConfigs(tenantId: string): Promise<AiConfig[]> {
  return unwrap(await api.get<ApiEnvelope<AiConfig[]>>("/ai/configs", { tenantId }));
}

/** Create or replace the config for a purpose. */
export async function upsertAiConfig(
  tenantId: string,
  payload: AiConfigUpsert,
): Promise<AiConfig> {
  return unwrap(await api.put<ApiEnvelope<AiConfig>>("/ai/configs", payload, { tenantId }));
}

export async function deleteAiConfig(tenantId: string, configId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`/ai/configs/${configId}`, { tenantId }));
}

export async function listAiUsage(
  tenantId: string,
  params?: AiUsageListParams,
): Promise<Page<AiUsage>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<AiUsage>>("/ai/usage", { query: { ...params }, tenantId }),
  );
}

export async function getAiUsageSummary(
  tenantId: string,
  range?: { since?: string | null; until?: string | null },
): Promise<AiUsageSummary> {
  return unwrap(
    await api.get<ApiEnvelope<AiUsageSummary>>("/ai/usage/summary", {
      query: { ...range },
      tenantId,
    }),
  );
}

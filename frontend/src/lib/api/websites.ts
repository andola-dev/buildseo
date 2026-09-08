/** Client websites — the sites a workspace promotes. */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  ClientWebsite,
  ClientWebsiteCreate,
  ClientWebsiteListParams,
  ClientWebsiteUpdate,
  PaginatedEnvelope,
  UUID,
} from "@/types/api";

const BASE = "/client-websites";

export async function listWebsites(
  tenantId: string,
  params?: ClientWebsiteListParams,
  signal?: AbortSignal,
): Promise<Page<ClientWebsite>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<ClientWebsite>>(BASE, {
      query: { ...params },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

export async function getWebsite(tenantId: string, websiteId: UUID): Promise<ClientWebsite> {
  return unwrap(
    await api.get<ApiEnvelope<ClientWebsite>>(`${BASE}/${websiteId}`, { tenantId }),
  );
}

export async function createWebsite(
  tenantId: string,
  payload: ClientWebsiteCreate,
): Promise<ClientWebsite> {
  return unwrap(await api.post<ApiEnvelope<ClientWebsite>>(BASE, payload, { tenantId }));
}

export async function updateWebsite(
  tenantId: string,
  websiteId: UUID,
  payload: ClientWebsiteUpdate,
): Promise<ClientWebsite> {
  return unwrap(
    await api.patch<ApiEnvelope<ClientWebsite>>(`${BASE}/${websiteId}`, payload, { tenantId }),
  );
}

export async function deleteWebsite(tenantId: string, websiteId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${websiteId}`, { tenantId }));
}

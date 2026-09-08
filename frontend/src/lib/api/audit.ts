/** The security and business audit trail. */

import { api } from "@/lib/api/http";
import { unwrapPage, type Page } from "@/lib/api/envelope";
import type { AuditLog, AuditLogListParams, PaginatedEnvelope } from "@/types/api";

export async function listAuditLogs(
  tenantId: string,
  params?: AuditLogListParams,
  signal?: AbortSignal,
): Promise<Page<AuditLog>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<AuditLog>>("/audit-logs", {
      query: { ...params },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

/*
 * The backend exposes no `/audit-logs/{id}` detail endpoint, so the event
 * drawer renders the row it already has — `AuditLogRead.metadata` carries the
 * structured context. Recorded in docs/API_CONTRACT.md under "Known gaps".
 */

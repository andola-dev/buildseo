"use client";

import { useQuery } from "@tanstack/react-query";

import { auditApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type { AuditLogListParams } from "@/types/api";

export function useAuditLogs(params: AuditLogListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.audit.list(tenantId, params),
    queryFn: ({ signal }) => auditApi.listAuditLogs(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

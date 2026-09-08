"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { tenantsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import type { TenantCreate, TenantUpdate } from "@/types/api";

/**
 * Create a workspace.
 *
 * The new workspace changes the user's membership list, so the session is
 * invalidated to pick it up — the switcher then offers it immediately.
 */
export function useCreateWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TenantCreate) => tenantsApi.createTenant(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.myTenants() });
    },
  });
}

export function useUpdateWorkspace(tenantId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TenantUpdate) => {
      if (!tenantId) throw new Error("No active workspace");
      return tenantsApi.updateTenant(tenantId, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspace.detail(tenantId) });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

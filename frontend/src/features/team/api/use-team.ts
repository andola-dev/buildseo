"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { tenantsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type { MembershipCreate, MembershipUpdate, TenantMemberListParams } from "@/types/api";

/**
 * Workspace members.
 *
 * Membership is workspace-scoped, so the active workspace id is part of both
 * the path and the query key.
 */
export function useMembers(params: TenantMemberListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.team.members(tenantId, params),
    queryFn: () => tenantsApi.listMembers(tenantId!, params),
    enabled: Boolean(tenantId),
  });
}

export function useAddMember() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: MembershipCreate) => tenantsApi.addMember(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.team.all(tenantId) });
    },
  });
}

export function useUpdateMember() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      membershipId,
      payload,
    }: {
      membershipId: string;
      payload: MembershipUpdate;
    }) => tenantsApi.updateMember(tenantId!, membershipId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.team.all(tenantId) });
      // The caller's own roles may have changed, which changes what the UI
      // offers them.
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

export function useRemoveMember() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (membershipId: string) => tenantsApi.removeMember(tenantId!, membershipId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.team.all(tenantId) });
    },
  });
}

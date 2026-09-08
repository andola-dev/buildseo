"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { rolesApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type { RoleCreate, RoleListParams, RoleUpdate } from "@/types/api";

/**
 * The permission catalogue.
 *
 * The role editor renders whatever the backend reports, so a permission added
 * server-side appears here without a frontend change (spec §34).
 */
export function usePermissionCatalog() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.roles.permissionCatalog(tenantId),
    queryFn: () => rolesApi.listPermissions(tenantId!),
    enabled: Boolean(tenantId),
    staleTime: 30 * 60_000,
  });
}

export function useRoles(params: RoleListParams = {}) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.roles.list(tenantId, params),
    queryFn: () => rolesApi.listRoles(tenantId!, { page_size: 100, ...params }),
    enabled: Boolean(tenantId),
  });
}

export function useRole(roleId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.roles.detail(tenantId, roleId ?? ""),
    queryFn: () => rolesApi.getRole(tenantId!, roleId!),
    enabled: Boolean(tenantId && roleId),
  });
}

export function useCreateRole() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: RoleCreate) => rolesApi.createRole(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles.all(tenantId) });
    },
  });
}

export function useUpdateRole() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ roleId, payload }: { roleId: string; payload: RoleUpdate }) =>
      rolesApi.updateRole(tenantId!, roleId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles.all(tenantId) });
      // The caller's effective permissions may have changed.
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

export function useDeleteRole() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (roleId: string) => rolesApi.deleteRole(tenantId!, roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles.all(tenantId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.team.all(tenantId) });
    },
  });
}

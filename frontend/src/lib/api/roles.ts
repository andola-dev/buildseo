/**
 * Roles and the permission catalogue.
 *
 * The catalogue returned by `/permissions` is what the role editor renders —
 * the frontend never hardcodes which permissions exist (spec §34).
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  PaginatedEnvelope,
  Permission,
  Role,
  RoleCreate,
  RoleListParams,
  RoleUpdate,
  UUID,
} from "@/types/api";

export async function listPermissions(tenantId: string): Promise<Permission[]> {
  return unwrap(
    await api.get<ApiEnvelope<Permission[]>>("/permissions", { tenantId }),
  );
}

export async function listRoles(
  tenantId: string,
  params?: RoleListParams,
): Promise<Page<Role>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Role>>("/roles", { query: { ...params }, tenantId }),
  );
}

export async function getRole(tenantId: string, roleId: UUID): Promise<Role> {
  return unwrap(await api.get<ApiEnvelope<Role>>(`/roles/${roleId}`, { tenantId }));
}

export async function createRole(tenantId: string, payload: RoleCreate): Promise<Role> {
  return unwrap(await api.post<ApiEnvelope<Role>>("/roles", payload, { tenantId }));
}

export async function updateRole(
  tenantId: string,
  roleId: UUID,
  payload: RoleUpdate,
): Promise<Role> {
  return unwrap(
    await api.patch<ApiEnvelope<Role>>(`/roles/${roleId}`, payload, { tenantId }),
  );
}

export async function deleteRole(tenantId: string, roleId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`/roles/${roleId}`, { tenantId }));
}

/** Workspaces and their membership. */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  Membership,
  MembershipCreate,
  MembershipUpdate,
  PageParams,
  PaginatedEnvelope,
  Tenant,
  TenantCreate,
  TenantMemberListParams,
  TenantUpdate,
  UUID,
} from "@/types/api";

export async function listTenants(params?: PageParams): Promise<Page<Tenant>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Tenant>>("/tenants", { query: { ...params } }),
  );
}

export async function createTenant(payload: TenantCreate): Promise<Tenant> {
  return unwrap(await api.post<ApiEnvelope<Tenant>>("/tenants", payload));
}

export async function getTenant(tenantId: UUID): Promise<Tenant> {
  return unwrap(await api.get<ApiEnvelope<Tenant>>(`/tenants/${tenantId}`, { tenantId }));
}

export async function updateTenant(tenantId: UUID, payload: TenantUpdate): Promise<Tenant> {
  return unwrap(
    await api.patch<ApiEnvelope<Tenant>>(`/tenants/${tenantId}`, payload, { tenantId }),
  );
}

/* -------------------------------------------------------------------------- */
/* Members                                                                    */
/* -------------------------------------------------------------------------- */

export async function listMembers(
  tenantId: UUID,
  params?: TenantMemberListParams,
): Promise<Page<Membership>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Membership>>(`/tenants/${tenantId}/members`, {
      query: { ...params },
      tenantId,
    }),
  );
}

export async function addMember(
  tenantId: UUID,
  payload: MembershipCreate,
): Promise<Membership> {
  return unwrap(
    await api.post<ApiEnvelope<Membership>>(`/tenants/${tenantId}/members`, payload, {
      tenantId,
    }),
  );
}

export async function updateMember(
  tenantId: UUID,
  membershipId: UUID,
  payload: MembershipUpdate,
): Promise<Membership> {
  return unwrap(
    await api.patch<ApiEnvelope<Membership>>(
      `/tenants/${tenantId}/members/${membershipId}`,
      payload,
      { tenantId },
    ),
  );
}

export async function removeMember(tenantId: UUID, membershipId: UUID): Promise<void> {
  unwrapAck(
    await api.del<ApiEnvelope<unknown>>(`/tenants/${tenantId}/members/${membershipId}`, {
      tenantId,
    }),
  );
}

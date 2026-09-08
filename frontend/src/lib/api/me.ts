/** The authenticated user's own profile, workspaces and password. */

import { api } from "@/lib/api/http";
import { unwrap, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  Me,
  PageParams,
  PaginatedEnvelope,
  PasswordChangeRequest,
  Tenant,
  User,
  UserUpdate,
} from "@/types/api";

/**
 * Load the session: user, workspaces and the effective permission set for the
 * active workspace. The backend recomputes permissions per request, so a
 * revoked role takes effect immediately.
 *
 * `tenantId` scopes the permission set; pass it whenever a workspace is active
 * so the returned permissions match the workspace the UI is showing.
 */
export async function getMe(tenantId?: string | null): Promise<Me> {
  return unwrap(
    await api.get<ApiEnvelope<Me>>("/me", tenantId ? { tenantId } : {}),
  );
}

export async function updateMe(payload: UserUpdate): Promise<User> {
  return unwrap(await api.patch<ApiEnvelope<User>>("/me", payload));
}

export async function changePassword(payload: PasswordChangeRequest): Promise<void> {
  await api.post<ApiEnvelope<unknown>>("/me/password", payload);
}

export async function listMyTenants(params?: PageParams): Promise<Page<Tenant>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Tenant>>("/me/tenants", { query: { ...params } }),
  );
}

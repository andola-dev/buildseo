/** Directory of users visible to the caller. */

import { api } from "@/lib/api/http";
import { unwrap, unwrapPage, type Page } from "@/lib/api/envelope";
import type { ApiEnvelope, PaginatedEnvelope, User, UserListParams, UUID } from "@/types/api";

export async function listUsers(
  params?: UserListParams,
  tenantId?: string | null,
): Promise<Page<User>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<User>>("/users", {
      query: { ...params },
      ...(tenantId ? { tenantId } : {}),
    }),
  );
}

export async function getUser(userId: UUID, tenantId?: string | null): Promise<User> {
  return unwrap(
    await api.get<ApiEnvelope<User>>(`/users/${userId}`, tenantId ? { tenantId } : {}),
  );
}

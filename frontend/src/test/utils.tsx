/* eslint-disable @typescript-eslint/no-explicit-any */
import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { vi } from "vitest";

import type { Me, PaginationMeta, TenantMembershipSummary, User } from "@/types/api";

/**
 * A `QueryClient` for tests: no retries and no cache carry-over, so a failing
 * query fails immediately and each test starts clean.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // gcTime must not be 0: an entry seeded with `setQueryData` has no
      // observer, so a 0 gc time would evict it before the assertion runs.
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithQuery(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & { queryClient?: QueryClient },
) {
  const queryClient = options?.queryClient ?? createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                   */
/* -------------------------------------------------------------------------- */

export const TENANT_A = "11111111-1111-4111-8111-111111111111";
export const TENANT_B = "22222222-2222-4222-8222-222222222222";

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "99999999-9999-4999-8999-999999999999",
    email: "seo@example.com",
    first_name: "Sam",
    last_name: "Okafor",
    full_name: "Sam Okafor",
    is_active: true,
    is_verified: true,
    last_login_at: "2026-09-01T10:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

export function makeMembership(
  overrides: Partial<TenantMembershipSummary> = {},
): TenantMembershipSummary {
  return {
    tenant_id: TENANT_A,
    tenant_name: "Acme Marketing",
    tenant_slug: "acme-marketing",
    status: "ACTIVE",
    is_owner: false,
    roles: ["seo_manager"],
    ...overrides,
  };
}

export function makeSession(overrides: Partial<Me> = {}): Me {
  return {
    user: makeUser(),
    active_tenant_id: TENANT_A,
    tenants: [
      makeMembership(),
      makeMembership({
        tenant_id: TENANT_B,
        tenant_name: "Growth Agency",
        tenant_slug: "growth-agency",
      }),
    ],
    permissions: [
      "campaign.read",
      "campaign.create",
      "publisher.read",
      "opportunity.read",
      "submission.read",
    ],
    ...overrides,
  };
}

export function makeMeta(overrides: Partial<PaginationMeta> = {}): PaginationMeta {
  return {
    page: 1,
    page_size: 25,
    total: 1,
    total_pages: 1,
    has_next: false,
    has_previous: false,
    ...overrides,
  };
}

/** Build a `fetch` `Response` for a stubbed API call. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Replace `globalThis.fetch` with a queue of scripted responses. */
export function stubFetchSequence(responses: (() => Response | Promise<Response>)[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  let index = 0;

  const spy = vi.fn(async (input: any, init?: RequestInit) => {
    calls.push({ url: String(input), ...(init ? { init } : {}) });
    const next = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (!next) throw new Error("stubFetchSequence: no response configured");
    return next();
  });

  globalThis.fetch = spy as unknown as typeof fetch;
  return { calls, spy };
}

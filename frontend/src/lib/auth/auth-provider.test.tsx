import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";

import { PermissionGate } from "@/components/shared/permission-gate";
import { AuthProvider, useAuth } from "@/lib/auth/auth-provider";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, getAccessToken } from "@/lib/api/token-store";
import { queryKeys } from "@/lib/query/keys";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useTenant } from "@/lib/tenant/use-tenant";
import {
  createTestQueryClient,
  jsonResponse,
  makeSession,
  TENANT_A,
  TENANT_B,
} from "@/test/utils";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

/** A probe that surfaces the provider's state as text for assertions. */
function Probe() {
  const { status, user, login, logout } = useAuth();
  const { activeTenantId, tenants, switchTenant, tenantVersion, tenantStatus } = useTenant();
  const { can } = usePermissions();

  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="email">{user?.email ?? "none"}</span>
      <span data-testid="tenant">{activeTenantId ?? "none"}</span>
      <span data-testid="tenant-count">{tenants.length}</span>
      <span data-testid="tenant-version">{tenantVersion}</span>
      <span data-testid="tenant-status">{tenantStatus}</span>
      <span data-testid="can-create">{String(can("campaign.create"))}</span>
      <span data-testid="can-approve">{String(can("submission.approve"))}</span>

      <PermissionGate permission="campaign.create">
        <button type="button">New campaign</button>
      </PermissionGate>
      <PermissionGate permission="submission.approve">
        <button type="button">Approve submission</button>
      </PermissionGate>

      <button type="button" onClick={() => void switchTenant(TENANT_B)}>
        Switch workspace
      </button>
      <button
        type="button"
        onClick={() =>
          void login({ email: "seo@example.com", password: "pw", remember: false })
        }
      >
        Sign in
      </button>
      {/*
        `logout` rethrows a failed request after clearing local state, and the
        real caller (`UserMenu`) catches it to show a toast. Catching here too
        keeps a deliberately-offline test from leaking an unhandled rejection
        into the run.
      */}
      <button type="button" onClick={() => void logout().catch(() => {})}>
        Sign out
      </button>
    </div>
  );
}

/**
 * Assert the exact status.
 *
 * `toHaveTextContent` matches substrings, and "unauthenticated" contains
 * "authenticated" — so an anchored pattern is required here.
 */
async function expectStatus(status: "loading" | "authenticated" | "unauthenticated") {
  await waitFor(() =>
    expect(screen.getByTestId("status")).toHaveTextContent(new RegExp(`^${status}$`)),
  );
}

function renderProvider(queryClient = createTestQueryClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  replace.mockClear();
});

describe("session bootstrap", () => {
  it("restores a session from the refresh cookie and loads permissions", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "fresh", expires_in: 900, active_tenant_id: TENANT_A });
      }
      if (url.endsWith("/me")) return jsonResponse({ data: makeSession() });
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");
    await waitFor(() =>
      expect(screen.getByTestId("email")).toHaveTextContent("seo@example.com"),
    );
    expect(screen.getByTestId("tenant")).toHaveTextContent(TENANT_A);
    expect(screen.getByTestId("tenant-count")).toHaveTextContent("2");
  });

  it("fetches the session once, with the workspace already scoped", async () => {
    const meCalls: (string | null)[] = [];

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({
          access_token: "fresh",
          expires_in: 900,
          active_tenant_id: TENANT_A,
        });
      }
      if (url.endsWith("/me")) {
        meCalls.push(new Headers(init?.headers).get("x-tenant-id"));
        return jsonResponse({ data: makeSession() });
      }
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");
    await waitFor(() =>
      expect(screen.getByTestId("email")).toHaveTextContent("seo@example.com"),
    );

    // Adopting the token's workspace before the query runs is what keeps this
    // to a single request: otherwise the key changes once the workspace is
    // read from the response and everything refetches.
    expect(meCalls).toEqual([TENANT_A]);
  });

  it("mints a workspace-scoped token when the restored token has none", async () => {
    const calls: string[] = [];
    let selected: string | null = null;

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      calls.push(url);

      if (url === "/api/session/refresh") {
        // Plain login/refresh issues a token with no `tid` claim.
        return jsonResponse({ access_token: "unscoped", expires_in: 900 });
      }

      if (url.endsWith("/auth/select-tenant")) {
        selected = JSON.parse(String(init?.body)).tenant_id as string;
        return jsonResponse({
          data: {
            access_token: "scoped",
            expires_in: 900,
            expires_at: new Date(Date.now() + 900_000).toISOString(),
            active_tenant_id: selected,
          },
        });
      }

      if (url.endsWith("/me")) {
        // `/me` reads permissions from the token's `tid`, not from the header,
        // so an unscoped token yields no workspace and no permissions.
        return jsonResponse({
          data: selected
            ? makeSession({ active_tenant_id: selected })
            : makeSession({ active_tenant_id: null, permissions: [] }),
        });
      }

      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");

    // Without the select-tenant call the UI would render with zero permissions
    // and hide every feature.
    await waitFor(() =>
      expect(screen.getByTestId("can-create")).toHaveTextContent("true"),
    );
    expect(selected).toBe(TENANT_A);
    expect(screen.getByTestId("tenant")).toHaveTextContent(TENANT_A);
  });

  it("reports the workspace as resolving, not absent, while adoption is in flight", async () => {
    let releaseSelect: (() => void) | null = null;
    const selectBlocked = new Promise<void>((resolve) => {
      releaseSelect = resolve;
    });

    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);

      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "unscoped", expires_in: 900 });
      }
      if (url.endsWith("/auth/select-tenant")) {
        // Hold the switch open to inspect the intermediate state.
        await selectBlocked;
        return jsonResponse({
          data: {
            access_token: "scoped",
            expires_in: 900,
            expires_at: new Date(Date.now() + 900_000).toISOString(),
            active_tenant_id: TENANT_A,
          },
        });
      }
      if (url.endsWith("/me")) {
        return jsonResponse({
          data: makeSession({ active_tenant_id: null, permissions: [] }),
        });
      }
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    // Wait until the session has actually loaded its memberships, so the
    // assertion below is about the adoption window rather than the earlier
    // pre-session one.
    await waitFor(() =>
      expect(screen.getByTestId("tenant-count")).toHaveTextContent("2"),
    );

    // The account plainly has workspaces, so this window must not be reported
    // as "none" — that is what made the guard flash "No workspace yet".
    expect(screen.getByTestId("tenant-status")).toHaveTextContent("resolving");

    await act(async () => {
      releaseSelect?.();
    });

    await waitFor(() =>
      expect(screen.getByTestId("tenant-status")).toHaveTextContent("ready"),
    );
  });

  it("reports 'none' when the account belongs to no workspace at all", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "t", expires_in: 900 });
      }
      return jsonResponse({
        data: makeSession({ tenants: [], active_tenant_id: null, permissions: [] }),
      });
    }) as unknown as typeof fetch;

    renderProvider();

    await waitFor(() =>
      expect(screen.getByTestId("tenant-status")).toHaveTextContent("none"),
    );
  });

  it("stops waiting and reports 'none' when every workspace is refused", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "unscoped", expires_in: 900 });
      }
      if (url.endsWith("/auth/select-tenant")) {
        return jsonResponse(
          { error: { code: "TENANT_ACCESS_DENIED", message: "denied" } },
          403,
        );
      }
      return jsonResponse({
        data: makeSession({ active_tenant_id: null, permissions: [] }),
      });
    }) as unknown as typeof fetch;

    renderProvider();

    // A permanently failing adoption must be terminal, not an endless spinner.
    await waitFor(() =>
      expect(screen.getByTestId("tenant-status")).toHaveTextContent("none"),
    );
  });

  it("does not retry workspace selection in a loop when it is refused", async () => {
    let selectCalls = 0;

    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);

      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "unscoped", expires_in: 900 });
      }
      if (url.endsWith("/auth/select-tenant")) {
        selectCalls += 1;
        return jsonResponse(
          { error: { code: "TENANT_ACCESS_DENIED", message: "denied" } },
          403,
        );
      }
      if (url.endsWith("/me")) {
        return jsonResponse({
          data: makeSession({ active_tenant_id: null, permissions: [] }),
        });
      }
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");
    await waitFor(() => expect(selectCalls).toBeGreaterThan(0));

    // Give any runaway effect a chance to fire before asserting.
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(selectCalls).toBe(1);
  });

  it("reports unauthenticated when there is no usable refresh cookie", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401),
    ) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("unauthenticated");
    expect(getAccessToken()).toBeNull();
  });
});

describe("RBAC in the UI", () => {
  it("shows only the actions the backend granted", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "t", expires_in: 900, active_tenant_id: TENANT_A });
      }
      // campaign.create granted; submission.approve withheld.
      return jsonResponse({ data: makeSession() });
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");

    await waitFor(() =>
      expect(screen.getByTestId("can-create")).toHaveTextContent("true"),
    );
    expect(screen.getByTestId("can-approve")).toHaveTextContent("false");

    expect(screen.getByRole("button", { name: "New campaign" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve submission" }),
    ).not.toBeInTheDocument();
  });
});

describe("workspace switching", () => {
  it("mints a scoped token, evicts tenant-scoped cache and refetches permissions", async () => {
    const requests: string[] = [];

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      requests.push(url);

      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "t-a", expires_in: 900, active_tenant_id: TENANT_A });
      }

      if (url.endsWith("/auth/select-tenant")) {
        return jsonResponse({
          data: {
            access_token: "t-b",
            expires_in: 900,
            expires_at: new Date(Date.now() + 900_000).toISOString(),
            active_tenant_id: TENANT_B,
          },
        });
      }

      if (url.endsWith("/me")) {
        // The permission set follows the workspace the header names.
        const tenant = new Headers(init?.headers).get("x-tenant-id");
        return jsonResponse({
          data: makeSession(
            tenant === TENANT_B
              ? { active_tenant_id: TENANT_B, permissions: ["campaign.read"] }
              : {},
          ),
        });
      }

      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    const { queryClient } = renderProvider();

    await expectStatus("authenticated");

    // Seed cache entries for the current workspace plus a global one.
    queryClient.setQueryData(queryKeys.publishers.list(TENANT_A, {}), { items: ["stale"] });
    queryClient.setQueryData(queryKeys.myTenants(), ["global"]);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Switch workspace" }));
    });

    await waitFor(() => expect(screen.getByTestId("tenant")).toHaveTextContent(TENANT_B));

    // The previous workspace's rows are gone, not merely stale.
    expect(queryClient.getQueryData(queryKeys.publishers.list(TENANT_A, {}))).toBeUndefined();
    // Global data survives the switch.
    expect(queryClient.getQueryData(queryKeys.myTenants())).toEqual(["global"]);

    // The switch requested a workspace-scoped token.
    expect(requests.some((url) => url.endsWith("/auth/select-tenant"))).toBe(true);
    expect(getAccessToken()).toBe("t-b");

    // Permissions were refetched for the new workspace and narrowed.
    await waitFor(() =>
      expect(screen.getByTestId("can-create")).toHaveTextContent("false"),
    );
    expect(
      screen.queryByRole("button", { name: "New campaign" }),
    ).not.toBeInTheDocument();

    // The content region's key changed, so tenant-scoped React state resets.
    expect(screen.getByTestId("tenant-version")).toHaveTextContent("1");
  });
});

describe("login and logout", () => {
  it("signs in through the session route and never exposes a refresh token", async () => {
    const bodies: string[] = [];

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      if (typeof init?.body === "string") bodies.push(init.body);

      if (url === "/api/session/refresh") {
        return jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "none" } }, 401);
      }
      if (url === "/api/session/login") {
        // The route handler returns only the access token by construction.
        return jsonResponse({
          access_token: "logged-in",
          expires_in: 900,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
          active_tenant_id: TENANT_A,
        });
      }
      if (url.endsWith("/me")) return jsonResponse({ data: makeSession() });
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("unauthenticated");

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    });

    await expectStatus("authenticated");

    expect(getAccessToken()).toBe("logged-in");
    // Nothing resembling a refresh token reached browser storage.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("logged-in");
    // The password was posted once, to our own session route only.
    expect(bodies.filter((body) => body.includes("password"))).toHaveLength(1);
  });

  it("clears the token and redirects to /login on sign-out", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "t", expires_in: 900, active_tenant_id: TENANT_A });
      }
      if (url === "/api/session/logout") return jsonResponse({ ok: true });
      return jsonResponse({ data: makeSession() });
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(getAccessToken()).toBeNull();
    await expectStatus("unauthenticated");
  });

  it("clears local state even when the logout request fails", async () => {
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/session/refresh") {
        return jsonResponse({ access_token: "t", expires_in: 900, active_tenant_id: TENANT_A });
      }
      if (url === "/api/session/logout") throw new TypeError("offline");
      return jsonResponse({ data: makeSession() });
    }) as unknown as typeof fetch;

    renderProvider();

    await expectStatus("authenticated");

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    });

    // A network failure must never leave the browser looking signed in.
    await waitFor(() => expect(getAccessToken()).toBeNull());
    expect(replace).toHaveBeenCalledWith("/login");
  });
});

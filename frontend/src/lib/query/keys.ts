/**
 * Query keys (spec §16).
 *
 * Every tenant-scoped key is built by `tenantKey`, which prefixes it with the
 * `"t"` sentinel and the workspace id:
 *
 *     ["t", tenantId, "publishers", { list: filters }]
 *
 * That shape is what makes tenant isolation mechanical rather than careful:
 * `isTenantScopedKey` can identify every workspace-owned cache entry exactly,
 * so switching workspace removes all of them and nothing else. Global keys
 * (the session, the workspace list) never carry the sentinel and therefore
 * survive a switch.
 */

import type { Query } from "@tanstack/react-query";

/** Marks a key as belonging to one workspace. */
export const TENANT_SCOPE = "t" as const;

/**
 * A key segment. `object` rather than `Record<string, unknown>` so the typed
 * filter interfaces (`PublisherListParams` and friends) can be passed straight
 * in — an interface without an index signature is not assignable to a Record.
 */
type KeyPart = string | number | boolean | null | undefined | object;

/** Build a tenant-scoped key. */
export function tenantKey(tenantId: string | null, ...parts: KeyPart[]): readonly unknown[] {
  return [TENANT_SCOPE, tenantId, ...parts] as const;
}

/** True for any key produced by `tenantKey`. */
export function isTenantScopedKey(key: readonly unknown[]): boolean {
  return key[0] === TENANT_SCOPE;
}

/** True for a key scoped to a specific workspace. */
export function isKeyForTenant(key: readonly unknown[], tenantId: string): boolean {
  return key[0] === TENANT_SCOPE && key[1] === tenantId;
}

/** Predicate for `queryClient.removeQueries`. */
export function tenantScopedQueryPredicate(query: Query): boolean {
  return isTenantScopedKey(query.queryKey);
}

/* -------------------------------------------------------------------------- */
/* Global keys                                                                */
/* -------------------------------------------------------------------------- */

export const queryKeys = {
  /**
   * The session. Keyed by workspace because the permission set the backend
   * returns depends on which workspace the access token is scoped to.
   */
  session: (tenantId: string | null) => ["session", tenantId] as const,

  /** Workspaces the user belongs to — deliberately not tenant-scoped. */
  myTenants: () => ["my-tenants"] as const,

  websites: {
    all: (tenantId: string | null) => tenantKey(tenantId, "websites"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "websites", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "websites", { detail: id }),
  },

  campaigns: {
    all: (tenantId: string | null) => tenantKey(tenantId, "campaigns"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "campaigns", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "campaigns", { detail: id }),
    stats: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "campaigns", { stats: id }),
  },

  publishers: {
    all: (tenantId: string | null) => tenantKey(tenantId, "publishers"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "publishers", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "publishers", { detail: id }),
    discoveryProviders: (tenantId: string | null) =>
      tenantKey(tenantId, "publishers", "discovery-providers"),
    discoveryRuns: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "publishers", "discovery-runs", { list: filters }),
  },

  opportunities: {
    all: (tenantId: string | null) => tenantKey(tenantId, "opportunities"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "opportunities", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "opportunities", { detail: id }),
    content: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "opportunities", { content: id }),
  },

  submissions: {
    all: (tenantId: string | null) => tenantKey(tenantId, "submissions"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "submissions", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "submissions", { detail: id }),
    stateMachine: (tenantId: string | null) =>
      tenantKey(tenantId, "submissions", "state-machine"),
    reviewQueue: (tenantId: string | null) =>
      tenantKey(tenantId, "submissions", "review-queue"),
  },

  team: {
    all: (tenantId: string | null) => tenantKey(tenantId, "team"),
    members: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "team", { members: filters }),
  },

  roles: {
    all: (tenantId: string | null) => tenantKey(tenantId, "roles"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "roles", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "roles", { detail: id }),
    permissionCatalog: (tenantId: string | null) =>
      tenantKey(tenantId, "roles", "permission-catalog"),
  },

  credentials: {
    all: (tenantId: string | null) => tenantKey(tenantId, "credentials"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "credentials", { list: filters }),
  },

  ai: {
    all: (tenantId: string | null) => tenantKey(tenantId, "ai"),
    configs: (tenantId: string | null) => tenantKey(tenantId, "ai", "configs"),
    usage: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "ai", "usage", { list: filters }),
    usageSummary: (tenantId: string | null, range: object) =>
      tenantKey(tenantId, "ai", "usage-summary", range),
  },

  audit: {
    all: (tenantId: string | null) => tenantKey(tenantId, "audit"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "audit", { list: filters }),
  },

  jobs: {
    all: (tenantId: string | null) => tenantKey(tenantId, "jobs"),
    list: (tenantId: string | null, filters: object) =>
      tenantKey(tenantId, "jobs", { list: filters }),
    detail: (tenantId: string | null, id: string) =>
      tenantKey(tenantId, "jobs", { detail: id }),
  },

  workspace: {
    detail: (tenantId: string | null) => tenantKey(tenantId, "workspace"),
  },

  security: {
    sessions: () => ["auth-sessions"] as const,
  },
} as const;

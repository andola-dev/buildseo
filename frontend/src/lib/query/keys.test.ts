import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import {
  isKeyForTenant,
  isTenantScopedKey,
  queryKeys,
  tenantKey,
  tenantScopedQueryPredicate,
  TENANT_SCOPE,
} from "@/lib/query/keys";
import { TENANT_A, TENANT_B } from "@/test/utils";

describe("tenantKey", () => {
  it("prefixes with the sentinel and workspace id", () => {
    expect(tenantKey(TENANT_A, "publishers", { list: { page: 2 } })).toEqual([
      TENANT_SCOPE,
      TENANT_A,
      "publishers",
      { list: { page: 2 } },
    ]);
  });

  it("recognises its own keys and only its own", () => {
    expect(isTenantScopedKey(queryKeys.campaigns.all(TENANT_A))).toBe(true);
    expect(isTenantScopedKey(queryKeys.session(TENANT_A))).toBe(false);
    expect(isTenantScopedKey(queryKeys.myTenants())).toBe(false);
  });

  it("distinguishes one workspace's keys from another's", () => {
    const key = queryKeys.publishers.list(TENANT_A, {});
    expect(isKeyForTenant(key, TENANT_A)).toBe(true);
    expect(isKeyForTenant(key, TENANT_B)).toBe(false);
  });

  it("scopes every resource family to the workspace", () => {
    const families = [
      queryKeys.websites.all(TENANT_A),
      queryKeys.campaigns.all(TENANT_A),
      queryKeys.publishers.all(TENANT_A),
      queryKeys.opportunities.all(TENANT_A),
      queryKeys.submissions.all(TENANT_A),
      queryKeys.submissions.reviewQueue(TENANT_A),
      queryKeys.team.all(TENANT_A),
      queryKeys.roles.all(TENANT_A),
      queryKeys.credentials.all(TENANT_A),
      queryKeys.ai.configs(TENANT_A),
      queryKeys.audit.all(TENANT_A),
      queryKeys.jobs.all(TENANT_A),
      queryKeys.workspace.detail(TENANT_A),
    ];

    for (const key of families) {
      expect(isTenantScopedKey(key), String(key)).toBe(true);
      expect(isKeyForTenant(key, TENANT_A)).toBe(true);
    }
  });

  it("leaves genuinely global keys unscoped, so a switch cannot evict them", () => {
    expect(isTenantScopedKey(queryKeys.myTenants())).toBe(false);
    expect(isTenantScopedKey(queryKeys.security.sessions())).toBe(false);
  });
});

describe("tenant cache eviction", () => {
  it("removes every workspace-scoped entry and keeps the global ones", () => {
    const client = new QueryClient();

    client.setQueryData(queryKeys.publishers.list(TENANT_A, {}), { items: ["A"] });
    client.setQueryData(queryKeys.campaigns.list(TENANT_A, {}), { items: ["A"] });
    client.setQueryData(queryKeys.submissions.list(TENANT_B, {}), { items: ["B"] });
    client.setQueryData(queryKeys.myTenants(), ["global"]);
    client.setQueryData(queryKeys.security.sessions(), ["global"]);

    client.removeQueries({ predicate: tenantScopedQueryPredicate });

    // Nothing tenant-owned survives — including the *other* workspace's data,
    // which is what stops a stale row appearing after a switch back.
    expect(client.getQueryData(queryKeys.publishers.list(TENANT_A, {}))).toBeUndefined();
    expect(client.getQueryData(queryKeys.campaigns.list(TENANT_A, {}))).toBeUndefined();
    expect(client.getQueryData(queryKeys.submissions.list(TENANT_B, {}))).toBeUndefined();

    expect(client.getQueryData(queryKeys.myTenants())).toEqual(["global"]);
    expect(client.getQueryData(queryKeys.security.sessions())).toEqual(["global"]);
  });

  it("keys the session per workspace so permissions cannot be read across tenants", () => {
    const client = new QueryClient();

    client.setQueryData(queryKeys.session(TENANT_A), { permissions: ["campaign.create"] });
    client.setQueryData(queryKeys.session(TENANT_B), { permissions: [] });

    expect(client.getQueryData(queryKeys.session(TENANT_A))).toEqual({
      permissions: ["campaign.create"],
    });
    expect(client.getQueryData(queryKeys.session(TENANT_B))).toEqual({ permissions: [] });
  });

  it("gives different filters different cache entries", () => {
    const client = new QueryClient();

    client.setQueryData(queryKeys.publishers.list(TENANT_A, { status: "QUALIFIED" }), ["q"]);
    client.setQueryData(queryKeys.publishers.list(TENANT_A, { status: "REJECTED" }), ["r"]);

    expect(
      client.getQueryData(queryKeys.publishers.list(TENANT_A, { status: "QUALIFIED" })),
    ).toEqual(["q"]);
    expect(
      client.getQueryData(queryKeys.publishers.list(TENANT_A, { status: "REJECTED" })),
    ).toEqual(["r"]);
  });
});

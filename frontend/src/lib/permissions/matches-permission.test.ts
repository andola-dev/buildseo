import { describe, expect, it } from "vitest";

import { matchesPermission } from "@/lib/permissions/use-permissions";

describe("matchesPermission", () => {
  it("matches an exact code", () => {
    expect(matchesPermission(new Set(["campaign.create"]), "campaign.create")).toBe(true);
    expect(matchesPermission(new Set(["campaign.read"]), "campaign.create")).toBe(false);
  });

  it("honours a resource wildcard", () => {
    const granted = new Set(["publisher.*"]);
    expect(matchesPermission(granted, "publisher.delete")).toBe(true);
    expect(matchesPermission(granted, "campaign.delete")).toBe(false);
  });

  it("honours a global wildcard", () => {
    expect(matchesPermission(new Set(["*"]), "submission.approve")).toBe(true);
  });

  it("denies against an empty grant set", () => {
    expect(matchesPermission(new Set(), "campaign.read")).toBe(false);
  });

  it("does not treat a bare resource name as a grant on its actions", () => {
    expect(matchesPermission(new Set(["publisher"]), "publisher.delete")).toBe(false);
  });

  it("does not let one resource's wildcard leak into another", () => {
    expect(matchesPermission(new Set(["submission.*"]), "credential.read")).toBe(false);
  });
});

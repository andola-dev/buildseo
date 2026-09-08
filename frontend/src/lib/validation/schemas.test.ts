import { describe, expect, it } from "vitest";

import {
  campaignSchema,
  clientWebsiteSchema,
  credentialSchema,
  loginSchema,
  normalizeUrl,
  omitEmpty,
  parseKeywords,
  passwordChangeSchema,
  roleSchema,
  websiteUrlSchema,
} from "@/lib/validation/schemas";

describe("loginSchema", () => {
  it("requires a well-formed email and a password", () => {
    expect(loginSchema.safeParse({ email: "", password: "", remember: false }).success).toBe(
      false,
    );
    expect(
      loginSchema.safeParse({ email: "not-an-email", password: "x", remember: false }).success,
    ).toBe(false);
    expect(
      loginSchema.safeParse({ email: "a@b.com", password: "x", remember: true }).success,
    ).toBe(true);
  });
});

describe("websiteUrlSchema", () => {
  it("accepts a bare host, since the backend normalises the domain itself", () => {
    expect(websiteUrlSchema.safeParse("example.com").success).toBe(true);
    expect(websiteUrlSchema.safeParse("https://example.com/path").success).toBe(true);
    expect(websiteUrlSchema.safeParse("  example.co.uk  ").success).toBe(true);
  });

  it("rejects a value with no dotted host", () => {
    expect(websiteUrlSchema.safeParse("localhost").success).toBe(false);
    expect(websiteUrlSchema.safeParse("not a url").success).toBe(false);
    expect(websiteUrlSchema.safeParse("").success).toBe(false);
  });
});

describe("normalizeUrl", () => {
  it("adds a scheme only when one is missing", () => {
    expect(normalizeUrl("example.com")).toBe("https://example.com");
    expect(normalizeUrl("http://example.com")).toBe("http://example.com");
    expect(normalizeUrl("HTTPS://example.com")).toBe("HTTPS://example.com");
    expect(normalizeUrl("  example.com  ")).toBe("https://example.com");
  });
});

describe("clientWebsiteSchema", () => {
  it("accepts the minimum the backend requires", () => {
    const result = clientWebsiteSchema.safeParse({
      name: "Acme",
      website_url: "acme.com",
      description: "",
      industry: "",
      target_country: "",
      target_language: "",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a one-character name", () => {
    const result = clientWebsiteSchema.safeParse({ name: "A", website_url: "acme.com" });
    expect(result.success).toBe(false);
  });

  it("rejects a country code longer than two characters", () => {
    const result = clientWebsiteSchema.safeParse({
      name: "Acme",
      website_url: "acme.com",
      target_country: "USA",
    });
    expect(result.success).toBe(false);
  });
});

describe("campaignSchema", () => {
  it("allows a null link target, since the field is optional on the API", () => {
    const result = campaignSchema.safeParse({
      client_website_id: "id",
      name: "Q4 listings",
      target_link_count: null,
    });
    expect(result.success).toBe(true);
  });

  it("rejects a fractional or zero link target", () => {
    expect(
      campaignSchema.safeParse({
        client_website_id: "id",
        name: "Q4",
        target_link_count: 2.5,
      }).success,
    ).toBe(false);

    expect(
      campaignSchema.safeParse({
        client_website_id: "id",
        name: "Q4",
        target_link_count: 0,
      }).success,
    ).toBe(false);
  });

  it("requires a client website", () => {
    expect(
      campaignSchema.safeParse({
        client_website_id: "",
        name: "Q4",
        target_link_count: null,
      }).success,
    ).toBe(false);
  });
});

describe("credentialSchema", () => {
  it("rejects an implausibly short key", () => {
    const result = credentialSchema.safeParse({
      provider: "openai",
      label: "Prod",
      secret: "short",
      verify: true,
    });
    expect(result.success).toBe(false);
  });

  it("accepts a realistic key", () => {
    const result = credentialSchema.safeParse({
      provider: "openai",
      label: "Prod",
      secret: "sk-0123456789abcdef",
      verify: false,
    });
    expect(result.success).toBe(true);
  });
});

describe("passwordChangeSchema", () => {
  it("reports the mismatch against the confirm field, not the new password", () => {
    const result = passwordChangeSchema.safeParse({
      current_password: "old-password",
      new_password: "a-long-enough-password",
      confirm_password: "a-different-password",
      revoke_other_sessions: true,
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["confirm_password"]);
    }
  });

  it("enforces the backend's minimum length", () => {
    const result = passwordChangeSchema.safeParse({
      current_password: "old",
      new_password: "short",
      confirm_password: "short",
      revoke_other_sessions: false,
    });
    expect(result.success).toBe(false);
  });
});

describe("roleSchema", () => {
  it("requires at least one permission", () => {
    const result = roleSchema.safeParse({
      slug: "reviewer",
      name: "Reviewer",
      permissions: [],
    });
    expect(result.success).toBe(false);
  });

  it("rejects a slug with uppercase or spaces", () => {
    expect(
      roleSchema.safeParse({ slug: "Bad Slug", name: "X", permissions: ["a.b"] }).success,
    ).toBe(false);
  });
});

describe("parseKeywords", () => {
  it("splits on commas and newlines and drops blanks", () => {
    expect(parseKeywords("saas directory,\n startup listing ,,\n\n b2b ")).toEqual([
      "saas directory",
      "startup listing",
      "b2b",
    ]);
  });

  it("returns an empty list for blank input", () => {
    expect(parseKeywords("   \n , ")).toEqual([]);
  });
});

describe("omitEmpty", () => {
  it("drops empty strings and undefined but keeps null, false and zero", () => {
    expect(
      omitEmpty({ a: "", b: undefined, c: null, d: false, e: 0, f: "keep" }),
    ).toEqual({ c: null, d: false, e: 0, f: "keep" });
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL } from "@/config/app";
import { ApiError } from "@/lib/api/errors";
import {
  __resetTransportState,
  api,
  apiRequest,
  buildQuery,
  setSessionExpiredHandler,
} from "@/lib/api/http";
import {
  clearAccessToken,
  getAccessToken,
  isAccessTokenExpiring,
  setAccessToken,
} from "@/lib/api/token-store";
import { jsonResponse, stubFetchSequence } from "@/test/utils";

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
});

describe("buildQuery", () => {
  it("omits empty values so a cleared filter disappears from the request", () => {
    expect(
      buildQuery({ page: 2, status: null, q: "", flag: false, sort: undefined }),
    ).toBe("?page=2&flag=false");
  });

  it("repeats a key for array values", () => {
    expect(buildQuery({ tag: ["a", "b"] })).toBe("?tag=a&tag=b");
  });

  it("returns an empty string when nothing survives", () => {
    expect(buildQuery({ a: null, b: "" })).toBe("");
    expect(buildQuery(undefined)).toBe("");
  });
});

describe("apiRequest", () => {
  it("targets the versioned API base and attaches no bearer when none is held", async () => {
    const { calls } = stubFetchSequence([() => jsonResponse({ data: { ok: true } })]);

    await apiRequest("/campaigns");

    expect(calls[0]?.url).toBe(`${API_BASE_URL}/campaigns`);
    const headers = new Headers(calls[0]?.init?.headers);
    expect(headers.has("authorization")).toBe(false);
  });

  it("attaches the in-memory bearer token", async () => {
    setAccessToken({ accessToken: "tok-123", expiresIn: 900 });
    const { calls } = stubFetchSequence([() => jsonResponse({ data: {} })]);

    await apiRequest("/me");

    expect(new Headers(calls[0]?.init?.headers).get("authorization")).toBe(
      "Bearer tok-123",
    );
  });

  it("sends the active workspace as X-Tenant-ID", async () => {
    setAccessToken({ accessToken: "tok", expiresIn: 900 });
    const { calls } = stubFetchSequence([() => jsonResponse({ data: [] })]);

    await apiRequest("/publishers", { tenantId: "tenant-9" });

    expect(new Headers(calls[0]?.init?.headers).get("x-tenant-id")).toBe("tenant-9");
  });

  it("never writes the access token to browser storage", async () => {
    setAccessToken({ accessToken: "super-secret", expiresIn: 900 });
    stubFetchSequence([() => jsonResponse({ data: {} })]);

    await apiRequest("/me");

    const dump = JSON.stringify({
      local: { ...window.localStorage },
      session: { ...window.sessionStorage },
    });
    expect(dump).not.toContain("super-secret");
  });

  it("returns undefined for a 204 rather than trying to parse a body", async () => {
    stubFetchSequence([() => new Response(null, { status: 204 })]);

    await expect(apiRequest("/campaigns/x")).resolves.toBeUndefined();
  });

  it("converts a transport failure into a network ApiError", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    await expect(apiRequest("/campaigns")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });

  it("throws an ApiError carrying the backend's code", async () => {
    stubFetchSequence([
      () =>
        jsonResponse(
          { error: { code: "RESOURCE_NOT_FOUND", message: "Campaign not found" } },
          404,
        ),
    ]);

    const error = await apiRequest("/campaigns/missing").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("RESOURCE_NOT_FOUND");
  });
});

describe("401 handling", () => {
  it("refreshes once and retries the original request", async () => {
    setAccessToken({ accessToken: "stale", expiresIn: 900 });

    const { calls } = stubFetchSequence([
      // 1. original request → 401
      () => jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401),
      // 2. session refresh → new token
      () => jsonResponse({ access_token: "fresh", expires_in: 900 }),
      // 3. retry → success
      () => jsonResponse({ data: { ok: true } }),
    ]);

    await expect(apiRequest("/me")).resolves.toEqual({ data: { ok: true } });

    expect(calls).toHaveLength(3);
    expect(calls[1]?.url).toBe("/api/session/refresh");
    expect(getAccessToken()).toBe("fresh");
    expect(new Headers(calls[2]?.init?.headers).get("authorization")).toBe("Bearer fresh");
  });

  it("does not loop when the retried request also returns 401", async () => {
    setAccessToken({ accessToken: "stale", expiresIn: 900 });
    setSessionExpiredHandler(() => {});

    const { calls } = stubFetchSequence([
      () => jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401),
      () => jsonResponse({ access_token: "fresh", expires_in: 900 }),
      () => jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401),
    ]);

    await expect(apiRequest("/me")).rejects.toBeInstanceOf(ApiError);

    // Exactly one refresh attempt: original, refresh, retry. No more.
    expect(calls).toHaveLength(3);
  });

  it("signs the user out and clears the token when refresh fails", async () => {
    setAccessToken({ accessToken: "stale", expiresIn: 900 });
    const onExpired = vi.fn();
    setSessionExpiredHandler(onExpired);

    stubFetchSequence([
      () => jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401),
      () => jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "no cookie" } }, 401),
    ]);

    await expect(apiRequest("/me")).rejects.toBeInstanceOf(ApiError);

    expect(onExpired).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it("shares one refresh across concurrent 401s", async () => {
    setAccessToken({ accessToken: "stale", expiresIn: 900 });

    let refreshCount = 0;
    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);

      if (url === "/api/session/refresh") {
        refreshCount += 1;
        return jsonResponse({ access_token: "fresh", expires_in: 900 });
      }

      // Any request still bearing the stale token gets a 401.
      return getAccessToken() === "stale"
        ? jsonResponse({ error: { code: "TOKEN_EXPIRED", message: "expired" } }, 401)
        : jsonResponse({ data: { ok: true } });
    }) as unknown as typeof fetch;

    await Promise.all([
      apiRequest("/campaigns"),
      apiRequest("/publishers"),
      apiRequest("/submissions"),
    ]);

    // Three concurrent 401s, one refresh — the single-flight guard.
    expect(refreshCount).toBe(1);
  });

  it("does not attempt a refresh for an anonymous request", async () => {
    const { calls } = stubFetchSequence([
      () => jsonResponse({ error: { code: "INVALID_CREDENTIALS", message: "bad" } }, 401),
    ]);

    await expect(
      apiRequest("/auth/register", { method: "POST", body: {}, anonymous: true }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(calls).toHaveLength(1);
  });
});

describe("token store", () => {
  it("reports an absent token as expiring", () => {
    clearAccessToken();
    expect(isAccessTokenExpiring()).toBe(true);
  });

  it("treats a token inside the skew window as expiring", () => {
    setAccessToken({ accessToken: "t", expiresIn: 5 });
    expect(isAccessTokenExpiring(15_000)).toBe(true);
  });

  it("treats a long-lived token as fresh", () => {
    setAccessToken({ accessToken: "t", expiresIn: 3600 });
    expect(isAccessTokenExpiring()).toBe(false);
  });
});

describe("convenience wrappers", () => {
  it("serialises a JSON body and sets the content type", async () => {
    const { calls } = stubFetchSequence([() => jsonResponse({ data: {} })]);

    await api.post("/campaigns", { name: "Q4 listings" });

    expect(calls[0]?.init?.method).toBe("POST");
    expect(calls[0]?.init?.body).toBe(JSON.stringify({ name: "Q4 listings" }));
    expect(new Headers(calls[0]?.init?.headers).get("content-type")).toBe(
      "application/json",
    );
  });
});

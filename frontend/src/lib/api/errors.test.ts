import { describe, expect, it } from "vitest";

import {
  ApiError,
  apiErrorFromBody,
  errorMessage,
  fieldErrorMap,
  isApiError,
  resolveMessage,
} from "@/lib/api/errors";

describe("apiErrorFromBody", () => {
  it("maps the backend's error envelope to friendly copy for known codes", () => {
    const error = apiErrorFromBody(403, {
      error: {
        code: "TENANT_ACCESS_DENIED",
        message: "You do not have access to this tenant",
      },
    });

    expect(error.status).toBe(403);
    expect(error.code).toBe("TENANT_ACCESS_DENIED");
    expect(error.message).toBe("You do not have access to this workspace.");
    expect(error.isForbidden).toBe(true);
  });

  it("falls back to the backend's own message for an unknown code", () => {
    const error = apiErrorFromBody(409, {
      error: { code: "SOME_NEW_CODE", message: "A newer rule was violated." },
    });

    expect(error.code).toBe("SOME_NEW_CODE");
    expect(error.message).toBe("A newer rule was violated.");
  });

  it("flattens FastAPI 422 detail into field issues, dropping the body prefix", () => {
    const error = apiErrorFromBody(422, {
      detail: [
        { loc: ["body", "name"], msg: "String should have at least 2 characters", type: "too_short" },
        { loc: ["body", "target", "count"], msg: "Input should be an integer", type: "int_type" },
        { loc: ["query", "page"], msg: "must be positive", type: "value_error" },
      ],
    });

    expect(error.status).toBe(422);
    expect(error.code).toBe("VALIDATION_ERROR");
    expect(error.details).toEqual([
      { field: "name", message: "String should have at least 2 characters", code: "too_short" },
      { field: "target.count", message: "Input should be an integer", code: "int_type" },
      { field: "page", message: "must be positive", code: "value_error" },
    ]);
  });

  it("reads field issues from a details.fields map", () => {
    const error = apiErrorFromBody(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Invalid",
        details: { fields: { domain: "That domain is already registered." } },
      },
    });

    expect(fieldErrorMap(error)).toEqual({
      domain: "That domain is already registered.",
    });
  });

  it("does not surface FastAPI's bare string detail to the user", () => {
    const error = apiErrorFromBody(404, { detail: "Not Found" });

    expect(error.message).toBe("We couldn't find what you were looking for.");
    expect(error.message).not.toContain("Not Found");
  });

  it("handles a non-object body without throwing", () => {
    const error = apiErrorFromBody(500, null);

    expect(error.status).toBe(500);
    expect(error.message).toBe("Something went wrong on our end. Please try again.");
  });
});

describe("ApiError classification", () => {
  it("treats 5xx, 429 and network failures as retryable, and 4xx as not", () => {
    const make = (status: number) =>
      new ApiError({ status, code: "X", message: "x" });

    expect(make(0).isRetryable).toBe(true);
    expect(make(500).isRetryable).toBe(true);
    expect(make(429).isRetryable).toBe(true);
    expect(make(403).isRetryable).toBe(false);
    expect(make(422).isRetryable).toBe(false);
    expect(make(404).isRetryable).toBe(false);
  });

  it("identifies a network failure by status 0", () => {
    const error = new ApiError({ status: 0, code: "NETWORK_ERROR", message: "x" });
    expect(error.isNetworkError).toBe(true);
  });
});

describe("resolveMessage", () => {
  it("prefers our copy over the backend's for a code we know", () => {
    expect(resolveMessage("INVALID_CREDENTIALS", "bad creds", 401)).toBe(
      "Unable to sign in. Please check your email and password.",
    );
  });

  it("uses the status fallback when there is neither code nor message", () => {
    expect(resolveMessage(undefined, undefined, 429)).toBe(
      "Too many requests. Please wait a moment and try again.",
    );
  });
});

describe("fieldErrorMap", () => {
  it("keeps the first issue per field and ignores non-ApiError values", () => {
    const error = apiErrorFromBody(422, {
      detail: [
        { loc: ["body", "name"], msg: "first", type: "a" },
        { loc: ["body", "name"], msg: "second", type: "b" },
      ],
    });

    expect(fieldErrorMap(error)).toEqual({ name: "first" });
    expect(fieldErrorMap(new Error("plain"))).toEqual({});
  });
});

describe("errorMessage", () => {
  it("returns a generic line for a non-Error value rather than leaking it", () => {
    expect(errorMessage({ secret: "token" })).toBe(
      "Something went wrong. Please try again.",
    );
  });

  it("passes an ApiError message through", () => {
    expect(errorMessage(new ApiError({ status: 404, code: "X", message: "Gone" }))).toBe(
      "Gone",
    );
  });
});

describe("isApiError", () => {
  it("narrows only real ApiError instances", () => {
    expect(isApiError(new ApiError({ status: 1, code: "c", message: "m" }))).toBe(true);
    expect(isApiError(new Error("nope"))).toBe(false);
    expect(isApiError({ status: 500 })).toBe(false);
  });
});

describe("isConnectivityError", () => {
  /**
   * The session route handlers proxy to FastAPI and report an unreachable
   * backend as a 503 carrying NETWORK_ERROR, so connectivity failures do not
   * all arrive as status 0.
   */
  it("recognises an unreachable service however it is reported", () => {
    const make = (status: number, code: string) =>
      new ApiError({ status, code, message: "x" });

    expect(make(0, "NETWORK_ERROR").isConnectivityError).toBe(true);
    expect(make(503, "NETWORK_ERROR").isConnectivityError).toBe(true);
    expect(make(504, "PROVIDER_TIMEOUT").isConnectivityError).toBe(true);
    expect(make(0, "TIMEOUT").isConnectivityError).toBe(true);
  });

  it("does not treat an application error as a connectivity problem", () => {
    const make = (status: number, code: string) =>
      new ApiError({ status, code, message: "x" });

    expect(make(401, "INVALID_CREDENTIALS").isConnectivityError).toBe(false);
    expect(make(403, "PERMISSION_DENIED").isConnectivityError).toBe(false);
    expect(make(500, "INTERNAL_ERROR").isConnectivityError).toBe(false);
  });
});

/**
 * The application's only HTTP transport.
 *
 * Everything the browser sends to FastAPI passes through `apiRequest`, which is
 * what makes these guarantees enforceable in one place:
 *
 * - the access token is attached from memory, never from storage;
 * - the active workspace travels as `X-Tenant-ID` (the backend re-validates
 *   membership, so this is context and not authorization — spec §9);
 * - a 401 triggers exactly one single-flight refresh and one retry;
 * - a failed refresh clears the session and redirects to `/login` once;
 * - every failure surfaces as an `ApiError` with user-safe copy.
 *
 * ESLint forbids `fetch` elsewhere in `src/` so this cannot be bypassed.
 */

import { API_BASE_URL, API_TIMEOUT_MS, SESSION_ROUTES } from "@/config/app";
import { ApiError, apiErrorFromBody } from "@/lib/api/errors";
import {
  clearAccessToken,
  getAccessToken,
  isAccessTokenExpiring,
  setAccessToken,
} from "@/lib/api/token-store";

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | (string | number)[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** Serialised as JSON. Use `undefined` for no body. */
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** Extra headers. `Authorization` and `X-Tenant-ID` are managed here. */
  headers?: Record<string, string>;
  /**
   * Workspace this request acts in. Omitted for tenant-independent endpoints
   * (`/auth/*`, `/me`, `/tenants`).
   */
  tenantId?: string | null;
  /** Skip the bearer header — used by the session routes themselves. */
  anonymous?: boolean;
  /** Internal: marks a request that has already been retried after a refresh. */
  _retried?: boolean;
  timeoutMs?: number;
}

/* -------------------------------------------------------------------------- */
/* Query serialisation                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Build a query string, dropping empty values so a cleared filter disappears
 * from the request rather than being sent as `status=`.
 */
export function buildQuery(query: Record<string, QueryValue> | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;

    if (Array.isArray(value)) {
      for (const item of value) {
        if (item === null || item === undefined || item === "") continue;
        params.append(key, String(item));
      }
      continue;
    }

    params.set(key, String(value));
  }

  const serialised = params.toString();
  return serialised ? `?${serialised}` : "";
}

/* -------------------------------------------------------------------------- */
/* Session recovery                                                           */
/* -------------------------------------------------------------------------- */

/** In-flight refresh, shared so concurrent 401s cause one refresh call. */
let refreshPromise: Promise<boolean> | null = null;

/** Set while redirecting, so a burst of failures produces one navigation. */
let signingOut = false;

type SessionExpiredHandler = () => void;
let onSessionExpired: SessionExpiredHandler | null = null;

/**
 * Register what should happen when the session cannot be recovered.
 *
 * `AuthProvider` supplies this so the redirect goes through the router and can
 * preserve the current path; the fallback below is used if nothing registered.
 */
export function setSessionExpiredHandler(handler: SessionExpiredHandler | null): void {
  onSessionExpired = handler;
}

function handleSessionExpired(): void {
  clearAccessToken();

  if (signingOut) return;
  signingOut = true;

  if (onSessionExpired) {
    onSessionExpired();
    // Allow a later expiry to redirect again once this one is handled.
    signingOut = false;
    return;
  }

  if (typeof window !== "undefined") {
    const next = `${window.location.pathname}${window.location.search}`;
    const target =
      next && next !== "/login"
        ? `/login?next=${encodeURIComponent(next)}`
        : "/login";
    window.location.assign(target);
  }
}

/**
 * Exchange the HTTP-only refresh cookie for a new access token.
 *
 * The call goes to this app's own session route, not to FastAPI: only the
 * Next.js server can read the refresh cookie. Concurrent callers await the same
 * promise, and the promise is cleared in `finally` so a later 401 can refresh
 * again — which together prevent the refresh loop spec §12 warns about.
 */
async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const response = await fetch(SESSION_ROUTES.refresh, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Send the HTTP-only refresh cookie to our own origin.
        credentials: "same-origin",
        cache: "no-store",
      });

      if (!response.ok) return false;

      const payload = (await response.json()) as {
        access_token?: string;
        expires_in?: number;
        expires_at?: string | null;
        active_tenant_id?: string | null;
      };

      if (!payload.access_token) return false;

      setAccessToken({
        accessToken: payload.access_token,
        ...(typeof payload.expires_in === "number"
          ? { expiresIn: payload.expires_in }
          : {}),
        expiresAt: payload.expires_at ?? null,
        activeTenantId: payload.active_tenant_id ?? null,
      });
      return true;
    } catch {
      // A network failure during refresh is not a session expiry; the caller
      // surfaces it as a network error and the user can retry.
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/** Reset transport-level state. Test helper; not used by application code. */
export function __resetTransportState(): void {
  refreshPromise = null;
  signingOut = false;
  onSessionExpired = null;
}

/* -------------------------------------------------------------------------- */
/* Transport                                                                  */
/* -------------------------------------------------------------------------- */

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) return undefined;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) {
    const text = await response.text().catch(() => "");
    return text.length > 0 ? { detail: text } : undefined;
  }

  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

/**
 * Perform one request and return the parsed body.
 *
 * `T` is the *envelope* type. Resource modules unwrap `{ data }` themselves so
 * that pagination metadata stays reachable where it is needed.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    query,
    signal,
    headers = {},
    tenantId,
    anonymous = false,
    _retried = false,
    timeoutMs = API_TIMEOUT_MS,
  } = options;

  // Refresh proactively when the held token is already past its useful life,
  // so the common case costs one request instead of a 401 plus a retry.
  if (!anonymous && !_retried && isAccessTokenExpiring() && getAccessToken() !== null) {
    await refreshSession();
  }

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");

  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }

  if (!anonymous) {
    const token = getAccessToken();
    if (token) requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  if (tenantId) {
    requestHeaders.set("X-Tenant-ID", tenantId);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);

  // Honour a caller-supplied signal alongside our timeout.
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) abortFromCaller();
    else signal.addEventListener("abort", abortFromCaller, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}${buildQuery(query)}`, {
      method,
      headers: requestHeaders,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (cause) {
    // A caller-initiated abort is not an error condition: TanStack Query
    // cancels queries routinely, and surfacing those would flash error UI.
    if (signal?.aborted) throw cause;

    if (cause instanceof DOMException && cause.name === "TimeoutError") {
      throw new ApiError({
        status: 0,
        code: "TIMEOUT",
        message: "The request took too long. Please try again.",
      });
    }

    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "We couldn't reach the server. Check your connection and try again.",
    });
  } finally {
    clearTimeout(timeout);
    if (signal) signal.removeEventListener("abort", abortFromCaller);
  }

  if (response.ok) {
    return (await readBody(response)) as T;
  }

  // One refresh, one retry. `_retried` is what stops a persistently-401
  // endpoint from looping.
  if (response.status === 401 && !anonymous && !_retried) {
    const refreshed = await refreshSession();

    if (refreshed) {
      return apiRequest<T>(path, { ...options, _retried: true });
    }

    handleSessionExpired();
  }

  throw apiErrorFromBody(response.status, await readBody(response));
}

/* -------------------------------------------------------------------------- */
/* Convenience wrappers                                                       */
/* -------------------------------------------------------------------------- */

type BodylessOptions = Omit<RequestOptions, "method" | "body">;
type BodyOptions = Omit<RequestOptions, "method">;

export const api = {
  get: <T>(path: string, options?: BodylessOptions) =>
    apiRequest<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: unknown, options?: BodyOptions) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),

  patch: <T>(path: string, body?: unknown, options?: BodyOptions) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),

  put: <T>(path: string, body?: unknown, options?: BodyOptions) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),

  del: <T>(path: string, options?: BodyOptions) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};

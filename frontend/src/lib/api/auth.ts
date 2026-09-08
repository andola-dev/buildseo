/**
 * Authentication.
 *
 * Login, refresh and logout are routed through this app's own
 * `/api/session/*` handlers rather than straight to FastAPI. The backend
 * returns a long-lived opaque refresh token in the response body; the session
 * routes keep it in an HTTP-only cookie so it never becomes readable to
 * browser scripts, and hand back only the short-lived access token, which the
 * client holds in memory (spec §12/§48).
 *
 * Everything else here talks to FastAPI directly with the bearer token.
 */

import { SESSION_ROUTES } from "@/config/app";
import { api, apiRequest } from "@/lib/api/http";
import { ApiError, apiErrorFromBody } from "@/lib/api/errors";
import { unwrap, unwrapAck } from "@/lib/api/envelope";
import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import type {
  AccessTokenResponse,
  ApiEnvelope,
  RegisterRequest,
  SelectTenantRequest,
  UserSession,
  UUID,
} from "@/types/api";

/** What a session route hands back: the access token, never the refresh token. */
export interface SessionTokenResponse {
  access_token: string;
  expires_in?: number;
  expires_at?: string | null;
  active_tenant_id?: string | null;
}

/**
 * Call one of this app's session routes.
 *
 * These are same-origin Next.js route handlers, so they bypass `apiRequest`
 * (different base URL, cookie credentials, and no bearer token to attach).
 */
async function sessionRequest(
  path: string,
  body?: unknown,
): Promise<SessionTokenResponse | null> {
  let response: Response;

  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "We couldn't reach the server. Check your connection and try again.",
    });
  }

  const payload: unknown = await response.json().catch(() => undefined);

  if (!response.ok) {
    throw apiErrorFromBody(response.status, payload);
  }

  return (payload as SessionTokenResponse | null) ?? null;
}

export interface LoginInput {
  email: string;
  password: string;
  /** Optional workspace to make active as part of signing in. */
  tenantId?: UUID | null;
  /**
   * Keep the session across browser restarts. This controls the lifetime of
   * the refresh cookie set by the session route; the backend's own token
   * lifetime is unaffected.
   */
  remember: boolean;
}

/**
 * Sign in.
 *
 * On success the access token is placed in the in-memory store and returned;
 * the refresh token stays in an HTTP-only cookie the browser cannot read.
 */
export async function login(input: LoginInput): Promise<SessionTokenResponse> {
  const tokens = await sessionRequest(SESSION_ROUTES.login, {
    email: input.email,
    password: input.password,
    tenant_id: input.tenantId ?? null,
    remember: input.remember,
  });

  if (!tokens?.access_token) {
    throw new ApiError({
      status: 0,
      code: "MALFORMED_RESPONSE",
      message: "We received an unexpected response from the server.",
    });
  }

  setAccessToken({
    accessToken: tokens.access_token,
    ...(typeof tokens.expires_in === "number" ? { expiresIn: tokens.expires_in } : {}),
    expiresAt: tokens.expires_at ?? null,
    activeTenantId: tokens.active_tenant_id ?? null,
  });

  return tokens;
}

/**
 * Restore a session on a cold page load using the refresh cookie.
 *
 * Returns `false` when there is no usable cookie, which the auth provider
 * treats as "not signed in" rather than as an error.
 */
export async function restoreSession(): Promise<boolean> {
  try {
    const tokens = await sessionRequest(SESSION_ROUTES.refresh);
    if (!tokens?.access_token) return false;

    setAccessToken({
      accessToken: tokens.access_token,
      ...(typeof tokens.expires_in === "number" ? { expiresIn: tokens.expires_in } : {}),
      expiresAt: tokens.expires_at ?? null,
      activeTenantId: tokens.active_tenant_id ?? null,
    });
    return true;
  } catch (error) {
    // A 401 here just means "no valid cookie". Anything else is a real fault
    // and should reach the caller so it isn't shown as a silent sign-out.
    if (error instanceof ApiError && (error.isUnauthorized || error.status === 400)) {
      return false;
    }
    throw error;
  }
}

/** Sign out: revoke server-side, clear the cookie, clear the in-memory token. */
export async function logout(options?: { allSessions?: boolean }): Promise<void> {
  try {
    await sessionRequest(SESSION_ROUTES.logout, {
      all_sessions: options?.allSessions ?? false,
    });
  } finally {
    // Local state is cleared even if the revoke call failed, so a network
    // problem can never leave the user apparently signed in.
    clearAccessToken();
  }
}

/**
 * Make a different workspace active.
 *
 * The backend validates membership and returns a new access token scoped to
 * the workspace. The refresh token is deliberately not rotated, so the session
 * cookie is untouched.
 */
export async function selectTenant(tenantId: UUID): Promise<AccessTokenResponse> {
  const body: SelectTenantRequest = { tenant_id: tenantId };
  const token = unwrap(
    await api.post<ApiEnvelope<AccessTokenResponse>>("/auth/select-tenant", body),
  );

  setAccessToken({
    accessToken: token.access_token,
    expiresIn: token.expires_in,
    expiresAt: token.expires_at,
    activeTenantId: token.active_tenant_id,
  });

  return token;
}

/** Register a new account, optionally creating its first workspace. */
export async function register(payload: RegisterRequest): Promise<void> {
  await apiRequest<unknown>("/auth/register", {
    method: "POST",
    body: payload,
    anonymous: true,
  });
}

/** List the current user's active sessions (Settings → Security). */
export async function listSessions(): Promise<UserSession[]> {
  return unwrap(await api.get<ApiEnvelope<UserSession[]>>("/auth/sessions"));
}

/** Revoke one session by id. */
export async function revokeSession(sessionId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`/auth/sessions/${sessionId}`));
}

/*
 * Not implemented by the backend, and intentionally absent from the UI
 * (spec §11/§72): password-reset-by-email and email verification. When those
 * endpoints exist, add them here — no call site outside this module changes.
 */

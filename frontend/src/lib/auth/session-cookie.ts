/**
 * Server-only helpers for the refresh-token cookie.
 *
 * The backend returns a long-lived opaque refresh token in the login response
 * body. Keeping that in `localStorage` would expose it to any script on the
 * page, so instead it is held in an HTTP-only, SameSite=Strict cookie that only
 * these route handlers can read. The browser gets the short-lived access token
 * and nothing else (spec §48).
 *
 * This module must never be imported from a Client Component.
 */

import "server-only";

import type { NextResponse } from "next/server";

export const REFRESH_COOKIE = "buildseo_rt";

/** Origin of the FastAPI service as seen from the Next.js server. */
export function backendOrigin(): string {
  const origin =
    process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return origin.replace(/\/+$/, "");
}

export function backendUrl(path: string): string {
  return `${backendOrigin()}/api/v1${path}`;
}

/**
 * The lifetime of the refresh cookie must not exceed the backend's own refresh
 * token lifetime; a longer cookie would just produce a confusing failed refresh.
 */
const DEFAULT_REMEMBER_DAYS = 14;

function rememberMaxAge(): number {
  const configured = Number.parseInt(process.env.SESSION_REMEMBER_DAYS ?? "", 10);
  const days = Number.isFinite(configured) && configured > 0 ? configured : DEFAULT_REMEMBER_DAYS;
  return days * 24 * 60 * 60;
}

/**
 * Attach the refresh token.
 *
 * With `remember` the cookie persists for the refresh-token lifetime; without
 * it the cookie is a session cookie that the browser drops on close. That is
 * what "Remember session" on the login form actually controls — the backend has
 * no such flag (spec §11).
 */
export function setRefreshCookie(
  response: NextResponse,
  refreshToken: string,
  remember: boolean,
): void {
  response.cookies.set({
    name: REFRESH_COOKIE,
    value: refreshToken,
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    ...(remember ? { maxAge: rememberMaxAge() } : {}),
  });
}

export function clearRefreshCookie(response: NextResponse): void {
  response.cookies.set({
    name: REFRESH_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

/**
 * Whether the caller asked to be remembered.
 *
 * Reflected back into the cookie on refresh so a rotated token keeps the
 * lifetime the user originally chose.
 */
export const REMEMBER_COOKIE = "buildseo_rt_persist";

export function setRememberCookie(response: NextResponse, remember: boolean): void {
  response.cookies.set({
    name: REMEMBER_COOKIE,
    value: remember ? "1" : "0",
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    ...(remember ? { maxAge: rememberMaxAge() } : {}),
  });
}

export function clearRememberCookie(response: NextResponse): void {
  response.cookies.set({
    name: REMEMBER_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

/** The token pair as returned by `/auth/login` and `/auth/refresh`. */
export interface BackendTokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in: number;
  expires_at: string;
  active_tenant_id?: string | null;
}

/**
 * The subset handed to the browser.
 *
 * `refresh_token` is absent by construction, not by omission at the call site.
 */
export interface ClientTokenResponse {
  access_token: string;
  expires_in: number;
  expires_at: string;
  active_tenant_id: string | null;
}

export function toClientTokens(pair: BackendTokenPair): ClientTokenResponse {
  return {
    access_token: pair.access_token,
    expires_in: pair.expires_in,
    expires_at: pair.expires_at,
    active_tenant_id: pair.active_tenant_id ?? null,
  };
}

/**
 * Forward the backend's error envelope unchanged.
 *
 * The backend guarantees its `message` is caller-safe, and the browser client
 * re-maps known codes to its own copy, so nothing internal is leaked by this.
 */
export function errorPayload(body: unknown, status: number): unknown {
  if (typeof body === "object" && body !== null && "error" in body) return body;
  return {
    error: {
      code: status === 401 ? "AUTHENTICATION_FAILED" : "HTTP_ERROR",
      message:
        status === 401
          ? "Unable to sign in. Please check your email and password."
          : "That request could not be completed.",
    },
  };
}

/**
 * Rotate the session.
 *
 * Reads the HTTP-only refresh cookie, exchanges it at
 * `POST /api/v1/auth/refresh`, stores the rotated refresh token and returns the
 * new access token. Called on a cold page load to restore a session, and by the
 * API client when a request comes back 401.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  backendUrl,
  clearRefreshCookie,
  clearRememberCookie,
  REFRESH_COOKIE,
  REMEMBER_COOKIE,
  setRefreshCookie,
  setRememberCookie,
  toClientTokens,
  type BackendTokenPair,
} from "@/lib/auth/session-cookie";

function noSession(): NextResponse {
  const response = NextResponse.json(
    { error: { code: "TOKEN_EXPIRED", message: "Your session has expired." } },
    { status: 401 },
  );
  // Drop a cookie the backend has rejected, so the next load doesn't retry it.
  clearRefreshCookie(response);
  clearRememberCookie(response);
  return response;
}

export async function POST(): Promise<NextResponse> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  const remember = store.get(REMEMBER_COOKIE)?.value === "1";

  if (!refreshToken) {
    // No cookie is the ordinary "not signed in" case, not a fault.
    return NextResponse.json(
      { error: { code: "TOKEN_EXPIRED", message: "Your session has expired." } },
      { status: 401 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl("/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
  } catch {
    // A transport failure must not clear the cookie: the session may well
    // still be valid, and dropping it would sign the user out on a blip.
    return NextResponse.json(
      {
        error: {
          code: "NETWORK_ERROR",
          message: "We couldn't reach the server. Check your connection and try again.",
        },
      },
      { status: 503 },
    );
  }

  if (!upstream.ok) return noSession();

  const payload: unknown = await upstream.json().catch(() => undefined);
  const pair = (payload as { data?: BackendTokenPair } | undefined)?.data;

  if (!pair?.access_token || !pair.refresh_token) return noSession();

  const response = NextResponse.json(toClientTokens(pair));
  setRefreshCookie(response, pair.refresh_token, remember);
  setRememberCookie(response, remember);
  return response;
}

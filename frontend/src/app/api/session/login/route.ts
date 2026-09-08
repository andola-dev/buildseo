/**
 * Sign in.
 *
 * Proxies `POST /api/v1/auth/login`, keeps the refresh token in an HTTP-only
 * cookie and returns only the short-lived access token to the browser.
 */

import { NextResponse } from "next/server";

import {
  backendUrl,
  errorPayload,
  setRefreshCookie,
  setRememberCookie,
  toClientTokens,
  type BackendTokenPair,
} from "@/lib/auth/session-cookie";

interface LoginBody {
  email?: unknown;
  password?: unknown;
  tenant_id?: unknown;
  remember?: unknown;
}

export async function POST(request: Request): Promise<NextResponse> {
  let body: LoginBody;
  try {
    body = (await request.json()) as LoginBody;
  } catch {
    return NextResponse.json(
      { error: { code: "VALIDATION_ERROR", message: "That request wasn't valid." } },
      { status: 400 },
    );
  }

  const email = typeof body.email === "string" ? body.email : "";
  const password = typeof body.password === "string" ? body.password : "";
  const tenantId = typeof body.tenant_id === "string" ? body.tenant_id : null;
  const remember = body.remember === true;

  if (!email || !password) {
    return NextResponse.json(
      {
        error: {
          code: "VALIDATION_ERROR",
          message: "Enter your email address and password.",
        },
      },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        ...(tenantId ? { tenant_id: tenantId } : {}),
      }),
      cache: "no-store",
    });
  } catch {
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

  const payload: unknown = await upstream.json().catch(() => undefined);

  if (!upstream.ok) {
    return NextResponse.json(errorPayload(payload, upstream.status), {
      status: upstream.status,
    });
  }

  const pair = (payload as { data?: BackendTokenPair } | undefined)?.data;

  if (!pair?.access_token || !pair.refresh_token) {
    return NextResponse.json(
      {
        error: {
          code: "MALFORMED_RESPONSE",
          message: "We received an unexpected response from the server.",
        },
      },
      { status: 502 },
    );
  }

  const response = NextResponse.json(toClientTokens(pair));
  setRefreshCookie(response, pair.refresh_token, remember);
  setRememberCookie(response, remember);
  return response;
}

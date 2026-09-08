/**
 * Register an account, optionally creating its first workspace.
 *
 * Proxies `POST /api/v1/auth/register`, which — like login — returns a
 * `TokenPair` containing a long-lived refresh token. It goes through this
 * handler for exactly the same reason login does: so the refresh token is
 * stored in an HTTP-only cookie and only the short-lived access token reaches
 * the browser.
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

interface RegisterBody {
  email?: unknown;
  password?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  tenant_name?: unknown;
  remember?: unknown;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

export async function POST(request: Request): Promise<NextResponse> {
  let body: RegisterBody;
  try {
    body = (await request.json()) as RegisterBody;
  } catch {
    return NextResponse.json(
      { error: { code: "VALIDATION_ERROR", message: "That request wasn't valid." } },
      { status: 400 },
    );
  }

  const email = optionalString(body.email);
  const password = typeof body.password === "string" ? body.password : "";

  if (!email || !password) {
    return NextResponse.json(
      {
        error: {
          code: "VALIDATION_ERROR",
          message: "Enter an email address and a password.",
        },
      },
      { status: 400 },
    );
  }

  const firstName = optionalString(body.first_name);
  const lastName = optionalString(body.last_name);
  const tenantName = optionalString(body.tenant_name);

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl("/auth/register"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        ...(firstName ? { first_name: firstName } : {}),
        ...(lastName ? { last_name: lastName } : {}),
        // Omitted rather than null: the backend only creates a workspace when
        // a name is supplied, and its slug is derived server-side.
        ...(tenantName ? { tenant_name: tenantName } : {}),
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

  const remember = body.remember === true;
  const response = NextResponse.json(toClientTokens(pair));
  setRefreshCookie(response, pair.refresh_token, remember);
  setRememberCookie(response, remember);
  return response;
}

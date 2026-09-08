/**
 * Sign out.
 *
 * Revokes the refresh token server-side, then clears the cookies. The cookies
 * are cleared even when the upstream call fails, so a network problem can never
 * leave a browser holding a live session token.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  backendUrl,
  clearRefreshCookie,
  clearRememberCookie,
  REFRESH_COOKIE,
} from "@/lib/auth/session-cookie";

interface LogoutBody {
  all_sessions?: unknown;
}

export async function POST(request: Request): Promise<NextResponse> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;

  let allSessions = false;
  try {
    const body = (await request.json()) as LogoutBody;
    allSessions = body.all_sessions === true;
  } catch {
    // An empty body is fine: default to revoking just this session.
  }

  if (refreshToken) {
    try {
      await fetch(backendUrl("/auth/logout"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken, all_sessions: allSessions }),
        cache: "no-store",
      });
    } catch {
      // Best effort. The token still expires on its own, and the cookie is
      // cleared below regardless.
    }
  }

  const response = NextResponse.json({ ok: true });
  clearRefreshCookie(response);
  clearRememberCookie(response);
  return response;
}

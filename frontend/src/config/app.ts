/**
 * Application configuration, resolved from environment variables.
 *
 * Only `NEXT_PUBLIC_*` values are readable in the browser, and only values that
 * are safe to publish live here. Backend secrets must never be exposed this way
 * (spec §48/§58).
 */

function readPublic(name: string, fallback: string): string {
  const value = process.env[name];
  return value && value.length > 0 ? value : fallback;
}

/** Origin of the FastAPI service, without a trailing slash. */
export const API_ORIGIN = readPublic(
  "NEXT_PUBLIC_API_URL",
  "http://localhost:8000",
).replace(/\/+$/, "");

/** Versioned API base path. Every resource module builds on this. */
export const API_BASE_URL = `${API_ORIGIN}/api/v1`;

export const APP_NAME = readPublic("NEXT_PUBLIC_APP_NAME", "BuildSEO");

export const APP_DESCRIPTION =
  "Discover, qualify and submit links to free online listing and directory sites.";

export const API_TIMEOUT_MS = Number.parseInt(
  readPublic("NEXT_PUBLIC_API_TIMEOUT_MS", "30000"),
  10,
);

/**
 * Session endpoints served by this Next.js app rather than by FastAPI.
 *
 * The backend issues a long-lived opaque refresh token in the login response
 * body. Rather than keeping that in browser storage, these route handlers hold
 * it in an HTTP-only cookie and proxy login/refresh/logout to FastAPI. The
 * access token stays in memory only. See `docs/FRONTEND_ARCHITECTURE.md` §6.
 */
export const SESSION_ROUTES = {
  login: "/api/session/login",
  refresh: "/api/session/refresh",
  logout: "/api/session/logout",
} as const;

/** Table page sizes offered in the UI (spec §54). */
export const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

/** Debounce for search inputs that hit the API (spec §53). */
export const SEARCH_DEBOUNCE_MS = 300;

/** localStorage keys. None of these ever hold a credential. */
export const STORAGE_KEYS = {
  sidebarCollapsed: "buildseo:sidebar-collapsed",
  activeTenant: "buildseo:active-tenant",
  tablePageSize: "buildseo:table-page-size",
} as const;

/**
 * The MVP promotes free directory listings only (spec §73). This flag exists so
 * the scope is asserted in one place instead of being implied by each screen.
 */
export const FREE_LISTINGS_ONLY = true;

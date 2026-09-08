/**
 * In-memory access-token store.
 *
 * The access token lives here and nowhere else — not `localStorage`, not
 * `sessionStorage`, not a global state library (spec §48). A page reload
 * therefore starts with no token and the session is re-established from the
 * HTTP-only refresh cookie held by the Next.js session routes.
 *
 * The long-lived refresh token never enters this module, or any browser-visible
 * storage: it is set as an HTTP-only cookie by `/api/session/*`.
 */

interface TokenState {
  accessToken: string | null;
  /** Epoch milliseconds at which the access token expires. */
  expiresAt: number | null;
  /** Workspace the current access token is scoped to. */
  activeTenantId: string | null;
}

const state: TokenState = {
  accessToken: null,
  expiresAt: null,
  activeTenantId: null,
};

type Listener = () => void;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** Subscribe to token changes (used to react to a forced sign-out). */
export function subscribeToTokens(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getAccessToken(): string | null {
  return state.accessToken;
}

export function getActiveTokenTenantId(): string | null {
  return state.activeTenantId;
}

export function setAccessToken(token: {
  accessToken: string;
  /** Lifetime in seconds, as reported by the backend. */
  expiresIn?: number;
  expiresAt?: string | null;
  activeTenantId?: string | null;
}): void {
  state.accessToken = token.accessToken;
  state.activeTenantId = token.activeTenantId ?? null;

  if (token.expiresAt) {
    const parsed = Date.parse(token.expiresAt);
    state.expiresAt = Number.isNaN(parsed) ? null : parsed;
  } else if (typeof token.expiresIn === "number") {
    state.expiresAt = Date.now() + token.expiresIn * 1000;
  } else {
    state.expiresAt = null;
  }

  emit();
}

export function clearAccessToken(): void {
  state.accessToken = null;
  state.expiresAt = null;
  state.activeTenantId = null;
  emit();
}

/**
 * Whether the held token is absent or within `skewMs` of expiry.
 *
 * Refreshing slightly early avoids a guaranteed 401 round-trip on a token that
 * is about to lapse mid-flight.
 */
export function isAccessTokenExpiring(skewMs = 15_000): boolean {
  if (!state.accessToken) return true;
  if (state.expiresAt === null) return false;
  return Date.now() >= state.expiresAt - skewMs;
}

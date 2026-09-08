"use client";

/**
 * Session, active workspace and permissions.
 *
 * These three live in one provider on purpose. The backend's access token is
 * *workspace-scoped* (`tid` claim) and the permission set it returns is
 * computed per workspace, so "who am I", "which workspace am I in" and "what
 * may I do" change together in a single atomic step. Splitting them across
 * providers would let the UI render one workspace's rows against another
 * workspace's permissions during the gap.
 *
 * The slices are still consumed separately — `useAuth`, `useTenant` and
 * `usePermissions` — so feature code depends only on what it needs.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { STORAGE_KEYS } from "@/config/app";
import { isApiError } from "@/lib/api/errors";
import type { ApiError } from "@/lib/api/errors";
import { setSessionExpiredHandler } from "@/lib/api/http";
import {
  clearAccessToken,
  getAccessToken,
  getActiveTokenTenantId,
} from "@/lib/api/token-store";
import * as authApi from "@/lib/api/auth";
import * as meApi from "@/lib/api/me";
import { queryKeys, tenantScopedQueryPredicate } from "@/lib/query/keys";
import { readLocal, removeLocal, writeLocal } from "@/lib/utils/storage";
import type { Me, TenantMembershipSummary, User } from "@/types/api";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  session: Me | null;
  /** Set when the session query itself failed (as opposed to being signed out). */
  sessionError: ApiError | null;
  refetchSession: () => Promise<unknown>;

  /** Workspaces the user belongs to. */
  tenants: TenantMembershipSummary[];
  activeTenantId: string | null;
  activeTenant: TenantMembershipSummary | null;
  /**
   * Increments on every workspace change. Used as a React `key` on the content
   * region so tenant-scoped component state (filters, selections, wizard
   * drafts) is discarded rather than carried across (spec §49).
   */
  tenantVersion: number;
  switchingTenant: boolean;

  permissions: ReadonlySet<string>;

  /**
   * Where workspace resolution has got to.
   *
   * `resolving` matters: a user with two or more workspaces gets a token with
   * no `tid` from login, so there is a window where the session has loaded but
   * no workspace is active yet. Treating that as "no workspace" would flash an
   * alarming empty state on every cold load.
   */
  tenantStatus: "resolving" | "ready" | "none";
  /** Set when no workspace could be entered at all. */
  tenantError: ApiError | null;

  login: (input: authApi.LoginInput) => Promise<void>;
  logout: (options?: { allSessions?: boolean }) => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Per-user key, so two accounts on one browser don't inherit each other's workspace. */
function activeTenantStorageKey(userId: string | null): string {
  return userId ? `${STORAGE_KEYS.activeTenant}:${userId}` : STORAGE_KEYS.activeTenant;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  /**
   * Whether a bearer token is held. A cold page load starts with none and the
   * bootstrap below tries to mint one from the HTTP-only refresh cookie.
   */
  const [hasToken, setHasToken] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [activeTenantId, setActiveTenantId] = useState<string | null>(null);
  const [tenantVersion, setTenantVersion] = useState(0);
  const [switchingTenant, setSwitchingTenant] = useState(false);
  const [tenantError, setTenantError] = useState<ApiError | null>(null);

  /** Guards against restoring twice under React Strict Mode's double effect. */
  const bootstrapStarted = useRef(false);

  useEffect(() => {
    if (bootstrapStarted.current) return;
    bootstrapStarted.current = true;

    let cancelled = false;

    void (async () => {
      try {
        const restored = await authApi.restoreSession();
        if (cancelled) return;

        setHasToken(restored);

        // Adopt the workspace the restored token is already scoped to, before
        // the session query runs. Without this the query would fire once with
        // no workspace, then again once the workspace was adopted from the
        // response — two requests and a visible loading flash on every cold
        // load. The stored preference can still override it below.
        if (restored) setActiveTenantId(getActiveTokenTenantId());
      } catch {
        // A transport failure here is reported by the session query below,
        // which has retry and an error state; treating it as "signed out"
        // would bounce the user to /login on a temporary blip.
        if (!cancelled) setHasToken(false);
      } finally {
        if (!cancelled) setBootstrapped(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * The session.
   *
   * Keyed by workspace so switching workspace produces a distinct cache entry
   * and cannot show the previous workspace's permissions. `activeTenantId` is
   * passed through as `X-Tenant-ID` so the permission set matches the workspace
   * the UI is about to render.
   */
  const sessionQuery = useQuery({
    queryKey: queryKeys.session(activeTenantId),
    queryFn: () => meApi.getMe(activeTenantId),
    enabled: bootstrapped && hasToken,
    staleTime: 60_000,
    retry: (failureCount, error) => {
      if (isApiError(error) && !error.isRetryable) return false;
      return failureCount < 2;
    },
  });

  const session = sessionQuery.data ?? null;

  /**
   * Adopt a workspace once the session arrives.
   *
   * `GET /me` derives `permissions` from the access token's `tid` claim, not
   * from the `X-Tenant-ID` header (see `app/api/v1/me.py::read_me`). A token
   * issued by plain login carries no `tid`, so simply setting local state would
   * leave the session with an empty permission set and the UI would hide every
   * feature. The workspace therefore has to be adopted by minting a scoped
   * token via `POST /auth/select-tenant`, after which `/me` reports that
   * workspace's permissions.
   */
  const adoptionAttempt = useRef<string | null>(null);

  useEffect(() => {
    if (!session) return;

    const memberships = session.tenants ?? [];
    if (memberships.length === 0) return;

    const isMember = (id: string | null | undefined): id is string =>
      typeof id === "string" && memberships.some((m) => m.tenant_id === id);

    const stored = readLocal(activeTenantStorageKey(session.user.id));

    // Preference order: the workspace the user last chose, then the one the
    // token is already scoped to, then their first workspace.
    const desired =
      (isMember(stored) ? stored : null) ??
      (isMember(session.active_tenant_id) ? session.active_tenant_id : null) ??
      memberships[0]?.tenant_id ??
      null;

    if (desired === null) return;

    // The token is already scoped to the workspace we want: just adopt it.
    if (session.active_tenant_id === desired) {
      if (activeTenantId !== desired) setActiveTenantId(desired);
      return;
    }

    // Mint a token for it. `adoptionAttempt` makes this at-most-once per
    // workspace, so a rejected selection cannot become a request loop.
    if (adoptionAttempt.current === desired) return;
    adoptionAttempt.current = desired;

    void (async () => {
      try {
        await authApi.selectTenant(desired);
        setActiveTenantId(desired);
        setTenantError(null);
        // The permission set belongs to the new token, so re-read the session.
        await queryClient.invalidateQueries({ queryKey: ["session"] });
      } catch (error) {
        // The workspace is no longer selectable (membership revoked, workspace
        // suspended). Forget the stored preference so the next pass tries the
        // next candidate, and record the failure so the UI can stop waiting
        // rather than sitting on a spinner forever.
        if (stored === desired) {
          removeLocal(activeTenantStorageKey(session.user.id));
        }
        setTenantError(isApiError(error) ? error : null);
      }
    })();
  }, [session, activeTenantId, queryClient]);

  /* ---------------------------------------------------------------------- */
  /* Session expiry                                                        */
  /* ---------------------------------------------------------------------- */

  const handleExpired = useCallback(() => {
    clearAccessToken();
    setHasToken(false);
    setActiveTenantId(null);
    adoptionAttempt.current = null;
    queryClient.clear();

    if (typeof window !== "undefined") {
      const next = `${window.location.pathname}${window.location.search}`;
      const target =
        next && !next.startsWith("/login")
          ? `/login?next=${encodeURIComponent(next)}`
          : "/login";
      router.replace(target);
    }
  }, [queryClient, router]);

  useEffect(() => {
    setSessionExpiredHandler(handleExpired);
    return () => setSessionExpiredHandler(null);
  }, [handleExpired]);

  /* ---------------------------------------------------------------------- */
  /* Actions                                                               */
  /* ---------------------------------------------------------------------- */

  const login = useCallback(
    async (input: authApi.LoginInput) => {
      const tokens = await authApi.login(input);

      // Start from a clean cache: the previous occupant of this tab may have
      // been a different user in a different workspace.
      queryClient.clear();
      adoptionAttempt.current = null;
      setTenantError(null);
      setActiveTenantId(tokens.active_tenant_id ?? null);
      setHasToken(true);
      setBootstrapped(true);
    },
    [queryClient],
  );

  const logout = useCallback(
    async (options?: { allSessions?: boolean }) => {
      try {
        await authApi.logout(options);
      } finally {
        setHasToken(false);
        setActiveTenantId(null);
        adoptionAttempt.current = null;
        setTenantError(null);
        queryClient.clear();
        router.replace("/login");
      }
    },
    [queryClient, router],
  );

  /**
   * Switch workspace (spec §9/§49).
   *
   * The order matters: get a token for the new workspace first, then *remove*
   * every tenant-scoped cache entry — remove rather than invalidate, so no
   * component can render the previous workspace's rows from cache while the new
   * fetch is still in flight — then let the session and page queries refetch.
   */
  const switchTenant = useCallback(
    async (tenantId: string) => {
      if (tenantId === activeTenantId) return;

      setSwitchingTenant(true);
      try {
        await authApi.selectTenant(tenantId);

        queryClient.removeQueries({ predicate: tenantScopedQueryPredicate });
        queryClient.removeQueries({ queryKey: ["session"] });

        adoptionAttempt.current = tenantId;
        setActiveTenantId(tenantId);
        setTenantVersion((version) => version + 1);

        if (session?.user.id) {
          writeLocal(activeTenantStorageKey(session.user.id), tenantId);
        }
      } finally {
        setSwitchingTenant(false);
      }
    },
    [activeTenantId, queryClient, session?.user.id],
  );

  /* ---------------------------------------------------------------------- */

  const status: AuthStatus = useMemo(() => {
    if (!bootstrapped) return "loading";
    if (!hasToken) return "unauthenticated";
    if (sessionQuery.isPending) return "loading";
    if (session) return "authenticated";

    // The query settled without data — a 401 the transport already handled, or
    // a hard failure. Either way this must not stay "loading": a failed session
    // fetch would otherwise leave the user on the boot splash forever with no
    // error and no way out. `AuthGuard` renders a retry panel for a retryable
    // `sessionError` and redirects to /login otherwise.
    return "unauthenticated";
  }, [bootstrapped, hasToken, session, sessionQuery.isPending]);

  const permissions = useMemo(
    () => new Set(session?.permissions ?? []),
    [session?.permissions],
  );

  const tenants = useMemo(() => session?.tenants ?? [], [session?.tenants]);

  const activeTenant = useMemo(
    () => tenants.find((tenant) => tenant.tenant_id === activeTenantId) ?? null,
    [tenants, activeTenantId],
  );

  const tenantStatus: "resolving" | "ready" | "none" = useMemo(() => {
    if (activeTenantId) return "ready";
    if (session && tenants.length === 0) return "none";
    // A failed adoption is terminal: stop waiting and let the UI say so.
    if (tenantError) return "none";
    return "resolving";
  }, [activeTenantId, session, tenants.length, tenantError]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: session?.user ?? null,
      session,
      sessionError:
        sessionQuery.isError && isApiError(sessionQuery.error) ? sessionQuery.error : null,
      refetchSession: () => sessionQuery.refetch(),
      tenants,
      activeTenantId,
      activeTenant,
      tenantVersion,
      switchingTenant,
      permissions,
      tenantStatus,
      tenantError,
      login,
      logout,
      switchTenant,
    }),
    [
      status,
      session,
      sessionQuery,
      tenants,
      activeTenantId,
      activeTenant,
      tenantVersion,
      switchingTenant,
      permissions,
      tenantStatus,
      tenantError,
      login,
      logout,
      switchTenant,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}

/** The session slice. */
export function useAuth() {
  const { status, user, session, sessionError, refetchSession, login, logout } =
    useAuthContext();
  return { status, user, session, sessionError, refetchSession, login, logout };
}

/** Whether a bearer token is currently held. Test/diagnostic helper. */
export function hasAccessToken(): boolean {
  return getAccessToken() !== null;
}

export { useAuthContext };

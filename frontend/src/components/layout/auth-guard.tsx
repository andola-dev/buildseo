"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Link2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/feedback/error-state";
import { useAuth } from "@/lib/auth/auth-provider";
import { useTenant } from "@/lib/tenant/use-tenant";

function BootSplash() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-3">
        <span className="bg-primary text-primary-foreground flex size-9 animate-pulse items-center justify-center rounded-lg">
          <Link2 className="size-4.5" aria-hidden />
        </span>
        <span className="text-muted-foreground text-sm">Loading your workspace…</span>
      </div>
    </div>
  );
}

/**
 * Gate for the authenticated area (spec §12).
 *
 * While the session is resolving a splash is shown rather than the dashboard
 * chrome, so an unauthenticated visitor never sees a flash of the application.
 * A hard session-query failure gets a retry affordance instead of a silent
 * bounce to `/login`, which would look like being signed out for no reason.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status, sessionError, refetchSession } = useAuth();
  const { tenants, tenantStatus, tenantError } = useTenant();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status !== "unauthenticated") return;
    // Hold position while a retryable failure is on screen; redirecting would
    // discard the retry affordance and read as an unexplained sign-out.
    if (sessionError?.isRetryable) return;

    const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${next}`);
  }, [status, sessionError, pathname, router]);

  if (status === "loading") return <BootSplash />;

  if (status === "unauthenticated") {
    // A retryable failure (network, 5xx) is not a sign-out: show the error with
    // a retry action instead of bouncing the user to /login, which would look
    // like being signed out for no reason.
    if (sessionError && sessionError.isRetryable) {
      return (
        <div className="flex min-h-dvh items-center justify-center p-6">
          <ErrorState
            error={sessionError}
            resource="your session"
            onRetry={() => void refetchSession()}
          />
        </div>
      );
    }
    return null;
  }

  /**
   * Signed in, but no workspace is active yet.
   *
   * Three distinct situations, which must not be conflated:
   *
   * - `resolving` — the session has loaded but the workspace-scoped token is
   *   still being minted. Every account with two or more workspaces passes
   *   through this on each cold load, so showing an empty state here would
   *   flash "No workspace yet" at users who plainly have one.
   * - `none` — the account genuinely belongs to no workspace, or none could be
   *   entered. This is the one case worth an explanation.
   * - `ready` — fall through and render the application.
   */
  if (tenantStatus === "resolving") return <BootSplash />;

  if (tenantStatus === "none") {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <div className="flex max-w-sm flex-col items-center gap-4 text-center">
          <h1 className="text-lg font-semibold">
            {tenants.length === 0 ? "No workspace yet" : "Can't open a workspace"}
          </h1>
          <p className="text-muted-foreground text-sm">
            {tenants.length === 0
              ? "Your account isn't a member of any workspace. Ask an owner to invite you, or create one to get started."
              : (tenantError?.message ??
                "None of your workspaces could be opened. They may have been suspended, or your membership removed.")}
          </p>
          <Button asChild size="sm">
            <Link href="/settings/workspace">Manage workspaces</Link>
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

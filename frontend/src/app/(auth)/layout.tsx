/**
 * Unauthenticated shell.
 *
 * Deliberately free of the dashboard chrome — no sidebar, no workspace
 * switcher, nothing that would need a session to render.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <div className="bg-muted/30 min-h-dvh">{children}</div>;
}

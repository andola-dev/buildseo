import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AuthGuard } from "@/components/layout/auth-guard";
import { SidebarProvider } from "@/components/layout/sidebar-context";
import { TenantScope } from "@/components/layout/tenant-scope";

/**
 * The authenticated shell (spec §5).
 *
 *   ┌──────────────────────────────────────────┐
 *   │ sidebar │ header                         │
 *   │         ├────────────────────────────────┤
 *   │         │ main content                   │
 *   └──────────────────────────────────────────┘
 *
 * The sidebar is a sibling of the content column rather than an overlay, so
 * collapsing it reflows the content without a navigation or remount.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <SidebarProvider>
        <div className="flex min-h-dvh">
          <AppSidebar />

          <div className="flex min-w-0 flex-1 flex-col">
            <AppHeader />
            <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
              {/* Keyed by workspace so tenant-scoped component state is
                  discarded on a switch rather than carried over (spec §49). */}
              <TenantScope>{children}</TenantScope>
            </main>
          </div>
        </div>
      </SidebarProvider>
    </AuthGuard>
  );
}

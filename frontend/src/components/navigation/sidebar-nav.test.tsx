import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SidebarNav } from "@/components/navigation/sidebar-nav";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

const permissions = vi.hoisted(() => ({ current: new Set<string>() }));
const tenantStatus = vi.hoisted(() => ({ current: "ready" as string }));

vi.mock("@/lib/permissions/use-permissions", () => ({
  usePermissions: () => ({
    permissions: permissions.current,
    can: (code?: string | null) => (code ? permissions.current.has(code) : true),
    canAny: () => true,
    canAll: () => true,
  }),
}));

vi.mock("@/lib/tenant/use-tenant", () => ({
  useTenant: () => ({ tenantStatus: tenantStatus.current }),
}));

/** The collapsed rail uses tooltips, which the real app provides in `Providers`. */
function renderNav(collapsed = false) {
  return render(
    <TooltipProvider>
      <SidebarNav collapsed={collapsed} />
    </TooltipProvider>,
  );
}

describe("SidebarNav", () => {
  it("explains an empty permission set instead of rendering a bare menu", () => {
    permissions.current = new Set();
    tenantStatus.current = "ready";

    renderNav();

    // The failure this guards against: every entry filtered away, leaving a
    // menu that reads as an app whose pages were never built.
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent(/no permissions/i);
    expect(notice).toHaveTextContent(/Every page still exists/i);
    expect(notice).toHaveTextContent(/server-side permissions problem/i);
  });

  it("stays silent while the workspace is still resolving", () => {
    permissions.current = new Set();
    tenantStatus.current = "resolving";

    renderNav();

    // An empty set mid-adoption is expected; warning about it would flash.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing when the backend granted something", () => {
    permissions.current = new Set(["campaign.read", "publisher.read"]);
    tenantStatus.current = "ready";

    renderNav();

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /campaigns/i })).toBeInTheDocument();
  });

  it("keeps the notice reachable on the collapsed icon rail", () => {
    permissions.current = new Set();
    tenantStatus.current = "ready";

    renderNav(true);

    expect(
      screen.getByRole("status", { name: /no permissions in this workspace/i }),
    ).toBeInTheDocument();
  });

  it("never unhides an entry the permission set does not cover", () => {
    permissions.current = new Set(["campaign.read"]);
    tenantStatus.current = "ready";

    renderNav();

    // The backend's answer stays authoritative (spec §32): the notice is an
    // explanation, never a grant.
    expect(screen.getByRole("button", { name: /campaigns/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /publishers/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /audit logs/i })).not.toBeInTheDocument();
  });
});

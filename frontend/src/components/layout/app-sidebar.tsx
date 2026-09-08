"use client";

import Link from "next/link";
import { Building2, Link2, PanelLeftClose, PanelLeftOpen, Settings, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SidebarNav } from "@/components/navigation/sidebar-nav";
import { WorkspaceSwitcher } from "@/components/navigation/workspace-switcher";
import { useSidebar } from "@/components/layout/sidebar-context";
import { APP_NAME } from "@/config/app";
import { cn } from "@/lib/utils/cn";

/**
 * The sticky footer (spec §8).
 *
 * `mt-auto` inside the flex column pins these three entries to the bottom
 * regardless of how tall the navigation above them is.
 */
function SidebarFooterNav({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const items = [
    { title: "Settings", href: "/settings", icon: Settings },
    { title: "User Profile", href: "/settings/profile", icon: User },
    { title: "Current Workspace", href: "/settings/workspace", icon: Building2 },
  ];

  return (
    <div className="mt-auto shrink-0">
      <Separator className="bg-sidebar-border" />
      <div className="space-y-0.5 p-2">
        {items.map((item) => {
          const Icon = item.icon;

          const link = (
            <Link
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                "focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50 focus-visible:outline-none",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {collapsed ? (
                <span className="sr-only">{item.title}</span>
              ) : (
                <span className="truncate">{item.title}</span>
              )}
            </Link>
          );

          if (!collapsed) return <div key={item.href}>{link}</div>;

          return (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>{link}</TooltipTrigger>
              <TooltipContent side="right">{item.title}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

function SidebarBrand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link
      href="/dashboard"
      className={cn(
        "flex h-(--header-height) shrink-0 items-center gap-2 px-3",
        "focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50 focus-visible:outline-none",
        collapsed && "justify-center px-0",
      )}
    >
      <span className="bg-sidebar-primary text-sidebar-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-md">
        <Link2 className="size-4" aria-hidden />
      </span>
      {collapsed ? (
        <span className="sr-only">{APP_NAME}</span>
      ) : (
        <span className="truncate text-sm font-semibold tracking-tight">{APP_NAME}</span>
      )}
    </Link>
  );
}

/** The sidebar body, shared by the desktop rail and the mobile drawer. */
function SidebarBody({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <SidebarBrand collapsed={collapsed} />
      <Separator className="bg-sidebar-border" />

      <div className={cn("shrink-0 p-2", collapsed && "px-1")}>
        <WorkspaceSwitcher collapsed={collapsed} />
      </div>
      <Separator className="bg-sidebar-border" />

      {/* Only the navigation scrolls, which is what keeps the footer pinned. */}
      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto py-2">
        <SidebarNav collapsed={collapsed} {...(onNavigate ? { onNavigate } : {})} />
      </div>

      <SidebarFooterNav collapsed={collapsed} {...(onNavigate ? { onNavigate } : {})} />
    </div>
  );
}

/**
 * The application sidebar (spec §6/§8/§43).
 *
 * Desktop: a fixed column whose width is a CSS variable, so collapsing is a
 * class change — no navigation, no remount, no refetch.
 * Mobile: a Sheet drawer with the same body.
 */
export function AppSidebar() {
  const { collapsed, toggleCollapsed, mobileOpen, setMobileOpen, isMobile } = useSidebar();

  if (isMobile) {
    return (
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="left"
          className="bg-sidebar text-sidebar-foreground w-72 gap-0 p-0"
          showCloseButton={false}
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">
            Primary navigation and workspace settings
          </SheetDescription>
          <SidebarBody collapsed={false} onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <aside
      data-collapsed={collapsed}
      style={{
        width: collapsed ? "var(--sidebar-width-icon)" : "var(--sidebar-width)",
      }}
      className={cn(
        "bg-sidebar text-sidebar-foreground border-sidebar-border relative hidden shrink-0 border-r md:flex md:flex-col",
        "transition-[width] duration-200 ease-out motion-reduce:transition-none",
      )}
    >
      <SidebarBody collapsed={collapsed} />

      {/* The collapse control sits on the sidebar's edge so it is reachable in
          both states without competing with the navigation for space. */}
      <Button
        variant="outline"
        size="icon-sm"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        title={`${collapsed ? "Expand" : "Collapse"} sidebar (Ctrl+B)`}
        className="bg-background absolute -right-3 top-[calc(var(--header-height)/2)] z-10 size-6 -translate-y-1/2 rounded-full shadow-xs"
      >
        {collapsed ? (
          <PanelLeftOpen className="size-3.5" aria-hidden />
        ) : (
          <PanelLeftClose className="size-3.5" aria-hidden />
        )}
      </Button>
    </aside>
  );
}

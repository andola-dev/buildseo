"use client";

import { Bell, PanelLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { useSidebar } from "@/components/layout/sidebar-context";
import { UserMenu } from "@/components/navigation/user-menu";
import { WorkspaceSwitcher } from "@/components/navigation/workspace-switcher";

/**
 * Notifications placeholder (spec §10).
 *
 * In-app notifications are not part of the MVP and the product sends no email
 * of any kind (spec §72). The control exists so the header layout is settled,
 * and says plainly that there is nothing here yet rather than implying a
 * feature that does not exist.
 */
function NotificationsButton() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Notifications">
          <Bell className="size-4" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <div className="space-y-1">
          <p className="text-sm font-medium">Notifications</p>
          <p className="text-muted-foreground text-sm">
            You&apos;re all caught up. In-app notifications aren&apos;t available yet.
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** The application header (spec §10). */
export function AppHeader() {
  const { isMobile, setMobileOpen } = useSidebar();

  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-30 flex h-(--header-height) shrink-0 items-center gap-2 border-b px-3 backdrop-blur sm:px-4">
      {isMobile ? (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
        >
          <PanelLeft className="size-4" aria-hidden />
        </Button>
      ) : null}

      <div className="min-w-0 flex-1">
        <Breadcrumbs />
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {/* The switcher also lives in the sidebar; on mobile the sidebar is a
            drawer, so the header carries it there. */}
        {isMobile ? (
          <div className="w-40">
            <WorkspaceSwitcher />
          </div>
        ) : null}

        <NotificationsButton />
        <ThemeToggle />
        <Separator orientation="vertical" className="mx-1 h-6" />
        <UserMenu compact={isMobile} />
      </div>
    </header>
  );
}

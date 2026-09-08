"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { SETTINGS_NAV } from "@/config/navigation";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { cn } from "@/lib/utils/cn";

/**
 * Settings sub-navigation (spec §31).
 *
 * A vertical rail on wide screens and a horizontal scroller on narrow ones, so
 * the sections stay reachable without the page needing its own layout at every
 * breakpoint. Entries are permission-filtered like the main navigation.
 */
export function SettingsNav() {
  const pathname = usePathname();
  const { can } = usePermissions();

  const items = SETTINGS_NAV.filter((item) => can(item.permission));

  return (
    <nav aria-label="Settings" className="lg:w-52 lg:shrink-0">
      <ul className="scrollbar-thin flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
        {items.map((item) => {
          const active = item.exact
            ? pathname === item.href
            : pathname === item.href || pathname.startsWith(`${item.href}/`);

          return (
            <li key={item.href} className="shrink-0 lg:shrink">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                  "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
                  active
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                {item.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

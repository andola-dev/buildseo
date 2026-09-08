"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isNavGroup, NAVIGATION, type NavEntry, type NavLeaf } from "@/config/navigation";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { cn } from "@/lib/utils/cn";

/**
 * Whether a nav entry is the current view.
 *
 * Filtered entries are the same route with different query state, so matching
 * has to consider the query string: on `/publishers?status=QUALIFIED` the
 * "Qualified" entry is active and "Publisher Database" is not.
 */
function useIsActive() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return (item: NavLeaf): boolean => {
    const [path, query] = item.href.split("?");
    if (path !== pathname) {
      // A detail route keeps its section highlighted: /publishers/abc → the
      // "Publisher Database" entry stays active.
      return !item.exact && !query && path !== undefined && pathname.startsWith(`${path}/`);
    }

    if (!query) {
      // The unfiltered entry is active only when no filter is applied.
      return item.exact ? searchParams.size === 0 : true;
    }

    const expected = new URLSearchParams(query);
    for (const [key, value] of expected) {
      if (searchParams.get(key) !== value) return false;
    }
    return true;
  };
}

const LINK_BASE =
  "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50 focus-visible:outline-none";

function NavLink({
  item,
  active,
  collapsed,
  onNavigate,
  nested = false,
}: {
  item: NavLeaf;
  active: boolean;
  collapsed: boolean;
  onNavigate?: () => void;
  nested?: boolean;
}) {
  const Icon = item.icon;

  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        LINK_BASE,
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
          : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
        collapsed && "justify-center px-0",
        nested && !collapsed && "pl-8 text-[13px]",
      )}
    >
      {Icon ? <Icon className="size-4 shrink-0" aria-hidden /> : null}
      {collapsed ? (
        <span className="sr-only">{item.title}</span>
      ) : (
        <span className="truncate">{item.title}</span>
      )}
    </Link>
  );

  // Collapsed rail relies on tooltips for labels (spec §45).
  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.title}</TooltipContent>
    </Tooltip>
  );
}

function NavGroupEntry({
  entry,
  collapsed,
  onNavigate,
}: {
  entry: Extract<NavEntry, { items: NavLeaf[] }>;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const isActive = useIsActive();
  const { can } = usePermissions();

  const items = entry.items.filter((item) => can(item.permission));
  if (items.length === 0) return null;

  const sectionActive = pathname.startsWith(entry.match);
  const Icon = entry.icon;

  /**
   * When collapsed there is no room for a nested list, so the group becomes a
   * single icon linking to its first entry, with the group name in a tooltip.
   */
  if (collapsed) {
    const primary = items[0];
    if (!primary) return null;
    return (
      <NavLink
        item={{ ...primary, title: entry.title, icon: Icon }}
        active={sectionActive}
        collapsed
        {...(onNavigate ? { onNavigate } : {})}
      />
    );
  }

  return (
    <Collapsible defaultOpen={sectionActive} className="group/collapsible">
      <CollapsibleTrigger
        className={cn(
          LINK_BASE,
          "w-full",
          sectionActive
            ? "text-sidebar-foreground font-medium"
            : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
        )}
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="flex-1 truncate text-left">{entry.title}</span>
        <ChevronRight
          className="size-3.5 shrink-0 opacity-60 transition-transform group-data-[state=open]/collapsible:rotate-90"
          aria-hidden
        />
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-0.5 space-y-0.5">
        {items.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={isActive(item)}
            collapsed={false}
            nested
            {...(onNavigate ? { onNavigate } : {})}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * The primary navigation tree (spec §7/§45).
 *
 * Entries are filtered by the permissions the backend returned, so a viewer
 * never sees a section that would 403. Nested groups collapse and the active
 * entry is always indicated.
 */
export function SidebarNav({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const isActive = useIsActive();
  const { can } = usePermissions();

  return (
    <nav aria-label="Main" className="space-y-1 px-2">
      {NAVIGATION.filter((entry) => can(entry.permission)).map((entry) =>
        isNavGroup(entry) ? (
          <NavGroupEntry
            key={entry.title}
            entry={entry}
            collapsed={collapsed}
            {...(onNavigate ? { onNavigate } : {})}
          />
        ) : (
          <NavLink
            key={entry.href}
            item={entry}
            active={isActive(entry)}
            collapsed={collapsed}
            {...(onNavigate ? { onNavigate } : {})}
          />
        ),
      )}
    </nav>
  );
}

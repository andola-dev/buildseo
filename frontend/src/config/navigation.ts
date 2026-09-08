/**
 * Sidebar navigation (spec §7 and §69).
 *
 * Navigation is data, not markup: `AppSidebar` renders whatever this exports,
 * filtered by the permissions the backend returned. A future module is one
 * entry here plus a `features/<module>` folder — which is what keeps the MVP
 * navigation uncluttered while staying extensible (spec §74).
 */

import {
  ClipboardCheck,
  FileSearch,
  Globe,
  LayoutDashboard,
  Link2,
  Megaphone,
  Search,
  Send,
  Shield,
  ScrollText,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PERM } from "@/config/permissions";

export interface NavLeaf {
  title: string;
  href: string;
  icon?: LucideIcon;
  /** Permission required to see this entry. Omitted means always visible. */
  permission?: string;
  /**
   * Exact match only. Used for parent links whose children are the same route
   * with different query state, so "All Campaigns" is not highlighted while
   * you are on "Active Campaigns".
   */
  exact?: boolean;
}

export interface NavGroup {
  title: string;
  icon: LucideIcon;
  /** Route prefix that marks the whole group as active. */
  match: string;
  permission?: string;
  items: NavLeaf[];
}

export type NavEntry = NavLeaf | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return "items" in entry;
}

/**
 * Filtered views are the canonical list route plus URL state rather than
 * separate pages, so every view is bookmarkable and there is one table
 * implementation per resource (spec §42).
 */
export const NAVIGATION: NavEntry[] = [
  {
    title: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    title: "Campaigns",
    icon: Megaphone,
    match: "/campaigns",
    permission: PERM.CAMPAIGN_READ,
    items: [
      { title: "All Campaigns", href: "/campaigns", exact: true },
      { title: "Active Campaigns", href: "/campaigns?status=ACTIVE" },
    ],
  },
  {
    title: "Publishers",
    icon: Globe,
    match: "/publishers",
    permission: PERM.PUBLISHER_READ,
    items: [
      { title: "Publisher Database", href: "/publishers", exact: true },
      {
        title: "Discovery",
        href: "/publishers/discovery",
        icon: Search,
        permission: PERM.PUBLISHER_DISCOVER,
      },
      { title: "Qualified", href: "/publishers?status=QUALIFIED" },
      { title: "Rejected", href: "/publishers?status=REJECTED" },
    ],
  },
  {
    title: "Opportunities",
    icon: Link2,
    match: "/opportunities",
    permission: PERM.OPPORTUNITY_READ,
    items: [
      { title: "All Opportunities", href: "/opportunities", exact: true },
      { title: "Recommended", href: "/opportunities?status=QUALIFIED" },
      { title: "Ready for Submission", href: "/opportunities?status=READY" },
    ],
  },
  {
    title: "Submissions",
    icon: Send,
    match: "/submissions",
    permission: PERM.SUBMISSION_READ,
    items: [
      { title: "All Submissions", href: "/submissions", exact: true },
      {
        title: "Pending Review",
        href: "/submissions?status=PENDING_APPROVAL",
        icon: ClipboardCheck,
      },
      { title: "Submitted", href: "/submissions?status=SUBMITTED" },
      { title: "Published", href: "/submissions?status=PUBLISHED" },
      { title: "Failed", href: "/submissions?status=FAILED" },
    ],
  },
  {
    title: "Client Websites",
    href: "/websites",
    icon: FileSearch,
    permission: PERM.CLIENT_WEBSITE_READ,
  },
  {
    title: "Team",
    icon: Users,
    match: "/team",
    permission: PERM.USER_READ,
    items: [
      { title: "Members", href: "/team", exact: true },
      {
        title: "Roles & Permissions",
        href: "/settings/roles",
        icon: Shield,
        permission: PERM.ROLE_READ,
      },
    ],
  },
  {
    title: "Audit Logs",
    href: "/audit",
    icon: ScrollText,
    permission: PERM.AUDIT_READ,
  },
];

/** Settings sub-navigation (spec §31). */
export const SETTINGS_NAV: NavLeaf[] = [
  { title: "General", href: "/settings/general", exact: true },
  { title: "Workspace", href: "/settings/workspace", permission: PERM.TENANT_READ },
  { title: "Team", href: "/team", permission: PERM.USER_READ },
  { title: "Roles & Permissions", href: "/settings/roles", permission: PERM.ROLE_READ },
  { title: "AI Providers", href: "/settings/ai", permission: PERM.CREDENTIAL_READ },
  {
    title: "Third-Party Integrations",
    href: "/settings/integrations",
    permission: PERM.INTEGRATION_READ,
  },
  { title: "Security", href: "/settings/security" },
  { title: "Audit Logs", href: "/audit", permission: PERM.AUDIT_READ },
];

/**
 * Route-segment titles used by the breadcrumb trail and the header. Dynamic
 * segments resolve to the record's own name at render time.
 */
export const ROUTE_TITLES: Record<string, string> = {
  dashboard: "Dashboard",
  websites: "Client Websites",
  campaigns: "Campaigns",
  publishers: "Publishers",
  discovery: "Discovery",
  opportunities: "Opportunities",
  submissions: "Submissions",
  team: "Team",
  audit: "Audit Logs",
  settings: "Settings",
  general: "General",
  workspace: "Workspace",
  roles: "Roles & Permissions",
  ai: "AI Providers",
  integrations: "Integrations",
  security: "Security",
  new: "New",
};

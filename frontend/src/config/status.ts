/**
 * The single status-badge vocabulary (spec §50).
 *
 * Every screen resolves a status through this module, so `QUALIFIED` looks the
 * same in the publisher table, the opportunity detail header and the campaign
 * funnel. Adding a colour here changes it everywhere; styling a status inline
 * in a feature component is the thing this prevents.
 */

import type { badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

/**
 * Semantic tone per status, keyed by the backend's raw enum value.
 *
 * - `success` — a good terminal or near-terminal outcome
 * - `info` — in progress, nothing required of the user
 * - `warning` — waiting on a human decision
 * - `danger` — failed or refused
 * - `muted` — inert (draft, archived, unknown)
 */
const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  // Lifecycle shared by websites, campaigns and tenants
  DRAFT: "muted",
  ACTIVE: "success",
  PAUSED: "warning",
  COMPLETED: "info",
  ARCHIVED: "muted",
  SUSPENDED: "danger",

  // Publishers and opportunities
  DISCOVERED: "info",
  QUALIFYING: "info",
  QUALIFIED: "success",
  SELECTED: "info",
  BLOCKED: "danger",
  EXPIRED: "muted",

  // Submissions
  READY: "info",
  IN_PROGRESS: "info",
  SUBMITTED: "info",
  PENDING_APPROVAL: "warning",
  PENDING_REVIEW: "warning",
  VERIFICATION_PENDING: "warning",
  PUBLISHED: "success",
  VERIFIED: "success",
  REJECTED: "danger",
  FAILED: "danger",

  // Content review
  APPROVED: "success",
  SUPERSEDED: "muted",

  // Credentials
  CONFIGURED: "info",
  INVALID: "danger",
  DISABLED: "muted",

  // Memberships
  INVITED: "warning",
  REMOVED: "muted",

  // Jobs and discovery runs
  PENDING: "muted",
  RUNNING: "info",
  SUCCEEDED: "success",
  CANCELLED: "muted",

  // Pricing / link type
  FREE: "success",
  PAID: "danger",
  MIXED: "warning",
  DOFOLLOW: "success",
  NOFOLLOW: "muted",
  UNKNOWN: "muted",
};

/** Badge tone for a status, defaulting to neutral for anything unrecognised. */
export function statusVariant(status: string | null | undefined): BadgeVariant {
  if (!status) return "muted";
  return STATUS_VARIANTS[status] ?? "outline";
}

/* -------------------------------------------------------------------------- */
/* Score thresholds                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Score bands used by `ScoreBadge` / `ScoreBar`.
 *
 * `spam` is inverted: a high spam score is bad. These are presentation bands
 * only — the backend decides whether a publisher actually qualifies.
 */
export type ScoreKind = "quality" | "relevance" | "authority" | "spam" | "opportunity";

export function scoreTone(
  kind: ScoreKind,
  score: number | null | undefined,
): "success" | "warning" | "danger" | "muted" {
  if (score === null || score === undefined || Number.isNaN(score)) return "muted";

  if (kind === "spam") {
    if (score <= 20) return "success";
    if (score <= 50) return "warning";
    return "danger";
  }

  if (score >= 70) return "success";
  if (score >= 40) return "warning";
  return "danger";
}

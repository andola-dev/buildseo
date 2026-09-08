/**
 * Runtime value lists for the backend's enums.
 *
 * The unions in `@/types/api` are compile-time only, but filter dropdowns and
 * permission matrices need iterable values. `allOf` ties the two together: if
 * the backend adds, removes or renames an enum member, `npm run codegen:api`
 * followed by `npm run typecheck` fails here rather than shipping a filter that
 * silently omits a status.
 */

import type {
  AiProvider,
  AiPurpose,
  CampaignStatus,
  ClientWebsiteStatus,
  ContentStatus,
  CredentialProviderType,
  CredentialStatus,
  LinkType,
  MembershipStatus,
  OpportunityStatus,
  OpportunityType,
  PricingType,
  PublisherCategory,
  PublisherStatus,
  SubmissionMethod,
  SubmissionStatus,
  TenantStatus,
} from "@/types/api";

/**
 * Returns the list unchanged, but only type-checks when it covers the union
 * exactly — no missing members and no members the union does not have.
 */
function allOf<U extends string>() {
  return <L extends readonly U[]>(
    list: Exclude<U, L[number]> extends never ? L : never,
  ): L => list;
}

export const CAMPAIGN_STATUSES = allOf<CampaignStatus>()([
  "DRAFT",
  "ACTIVE",
  "PAUSED",
  "COMPLETED",
  "ARCHIVED",
] as const);

export const CLIENT_WEBSITE_STATUSES = allOf<ClientWebsiteStatus>()([
  "ACTIVE",
  "PAUSED",
  "ARCHIVED",
] as const);

export const PUBLISHER_STATUSES = allOf<PublisherStatus>()([
  "DISCOVERED",
  "QUALIFYING",
  "QUALIFIED",
  "REJECTED",
  "BLOCKED",
  "ARCHIVED",
] as const);

export const PUBLISHER_CATEGORIES = allOf<PublisherCategory>()([
  "BUSINESS_DIRECTORY",
  "LOCAL_DIRECTORY",
  "COMPANY_LISTING",
  "STARTUP_DIRECTORY",
  "SOFTWARE_DIRECTORY",
  "INDUSTRY_DIRECTORY",
  "ORGANIZATION_LISTING",
  "PROFILE_LISTING",
  "REVIEW_PLATFORM",
  "EVENT_LISTING",
  "JOB_BOARD",
  "OTHER",
] as const);

export const OPPORTUNITY_STATUSES = allOf<OpportunityStatus>()([
  "DISCOVERED",
  "QUALIFYING",
  "QUALIFIED",
  "REJECTED",
  "SELECTED",
  "READY",
  "SUBMITTED",
  "PUBLISHED",
  "FAILED",
  "EXPIRED",
] as const);

export const OPPORTUNITY_TYPES = allOf<OpportunityType>()([
  "FREE_DIRECTORY_LISTING",
  "FREE_LOCAL_LISTING",
  "FREE_COMPANY_PROFILE",
  "FREE_STARTUP_LISTING",
  "FREE_SOFTWARE_LISTING",
  "FREE_INDUSTRY_LISTING",
  "FREE_ORGANIZATION_LISTING",
  "FREE_PROFILE_LISTING",
] as const);

export const SUBMISSION_STATUSES = allOf<SubmissionStatus>()([
  "READY",
  "IN_PROGRESS",
  "SUBMITTED",
  "PENDING_APPROVAL",
  "PUBLISHED",
  "VERIFICATION_PENDING",
  "VERIFIED",
  "REJECTED",
  "FAILED",
] as const);

export const SUBMISSION_METHODS = allOf<SubmissionMethod>()([
  "MANUAL",
  "FORM",
  "EMAIL",
  "API",
  "ACCOUNT_REQUIRED",
  "UNKNOWN",
] as const);

export const CONTENT_STATUSES = allOf<ContentStatus>()([
  "DRAFT",
  "PENDING_REVIEW",
  "APPROVED",
  "REJECTED",
  "SUPERSEDED",
] as const);

export const CREDENTIAL_STATUSES = allOf<CredentialStatus>()([
  "CONFIGURED",
  "VERIFIED",
  "INVALID",
  "DISABLED",
] as const);

export const CREDENTIAL_PROVIDER_TYPES = allOf<CredentialProviderType>()([
  "AI",
  "SEARCH",
  "SEO_METRICS",
  "WEBSITE_INTELLIGENCE",
  "OTHER",
] as const);

export const MEMBERSHIP_STATUSES = allOf<MembershipStatus>()([
  "ACTIVE",
  "INVITED",
  "SUSPENDED",
  "REMOVED",
] as const);

export const TENANT_STATUSES = allOf<TenantStatus>()([
  "ACTIVE",
  "SUSPENDED",
  "ARCHIVED",
] as const);

export const PRICING_TYPES = allOf<PricingType>()([
  "FREE",
  "PAID",
  "MIXED",
  "UNKNOWN",
] as const);

export const LINK_TYPES = allOf<LinkType>()([
  "DOFOLLOW",
  "NOFOLLOW",
  "MIXED",
  "UNKNOWN",
] as const);

export const AI_PROVIDERS = allOf<AiProvider>()([
  "openai",
  "anthropic",
  "gemini",
  "openrouter",
  "custom",
] as const);

export const AI_PURPOSES = allOf<AiPurpose>()([
  "content_generation",
  "discovery",
  "qualification",
  "embedding",
] as const);

/**
 * The MVP promotes free listings only (spec §73), so the publisher list and
 * every discovery request are pinned to FREE pricing. Paid, MIXED and UNKNOWN
 * exist in the backend enum but are never offered as a choice in the UI.
 */
export const MVP_PRICING_TYPE = "FREE" satisfies PricingType;

/** Opportunity statuses that mean "the human has not decided yet". */
export const OPPORTUNITY_PENDING_STATUSES: readonly OpportunityStatus[] = [
  "DISCOVERED",
  "QUALIFYING",
  "QUALIFIED",
];

/** Submission statuses that still need a reviewer. */
export const SUBMISSION_REVIEW_STATUSES: readonly SubmissionStatus[] = [
  "READY",
  "PENDING_APPROVAL",
];

/** Submission statuses past which no further action is expected. */
export const SUBMISSION_TERMINAL_STATUSES: readonly SubmissionStatus[] = [
  "VERIFIED",
  "REJECTED",
  "FAILED",
];

/* -------------------------------------------------------------------------- */
/* Statuses the backend serialises as a bare string                           */
/*                                                                            */
/* DiscoveryRunRead.status and JobRead.status are typed `str` in the OpenAPI   */
/* document rather than as enum refs, so codegen cannot narrow them. These     */
/* mirror app/core/enums.py — DiscoveryRunStatus and JobStatus.                */
/* -------------------------------------------------------------------------- */

export const DISCOVERY_RUN_STATUSES = [
  "PENDING",
  "RUNNING",
  "COMPLETED",
  "FAILED",
] as const;
export type DiscoveryRunStatus = (typeof DISCOVERY_RUN_STATUSES)[number];

export const JOB_STATUSES = [
  "PENDING",
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

/** Statuses that mean a discovery run or job is still working, so keep polling. */
export const IN_FLIGHT_STATUSES: readonly string[] = ["PENDING", "RUNNING"];

/** Statuses that mean a discovery run or job has finished, so stop polling. */
export function isTerminalRunStatus(status: string): boolean {
  return !IN_FLIGHT_STATUSES.includes(status);
}

/** Seeded role slugs (app/core/enums.py — SystemRoleSlug). */
export const SYSTEM_ROLE_SLUGS = [
  "owner",
  "admin",
  "seo_manager",
  "seo_specialist",
  "viewer",
] as const;
export type SystemRoleSlug = (typeof SYSTEM_ROLE_SLUGS)[number];

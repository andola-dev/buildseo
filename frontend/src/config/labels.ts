/**
 * Human-readable labels for the backend's SCREAMING_SNAKE_CASE enum values.
 *
 * Labels live here rather than inline so a status reads identically in a table
 * cell, a filter dropdown and a detail header.
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

export const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, string> = {
  DRAFT: "Draft",
  ACTIVE: "Active",
  PAUSED: "Paused",
  COMPLETED: "Completed",
  ARCHIVED: "Archived",
};

export const CLIENT_WEBSITE_STATUS_LABELS: Record<ClientWebsiteStatus, string> = {
  ACTIVE: "Active",
  PAUSED: "Paused",
  ARCHIVED: "Archived",
};

export const PUBLISHER_STATUS_LABELS: Record<PublisherStatus, string> = {
  DISCOVERED: "Discovered",
  QUALIFYING: "Qualifying",
  QUALIFIED: "Qualified",
  REJECTED: "Rejected",
  BLOCKED: "Blocked",
  ARCHIVED: "Archived",
};

export const PUBLISHER_CATEGORY_LABELS: Record<PublisherCategory, string> = {
  BUSINESS_DIRECTORY: "Business directory",
  LOCAL_DIRECTORY: "Local directory",
  COMPANY_LISTING: "Company listing",
  STARTUP_DIRECTORY: "Startup directory",
  SOFTWARE_DIRECTORY: "Software directory",
  INDUSTRY_DIRECTORY: "Industry directory",
  ORGANIZATION_LISTING: "Organization listing",
  PROFILE_LISTING: "Profile listing",
  REVIEW_PLATFORM: "Review platform",
  EVENT_LISTING: "Event listing",
  JOB_BOARD: "Job board",
  OTHER: "Other",
};

export const OPPORTUNITY_STATUS_LABELS: Record<OpportunityStatus, string> = {
  DISCOVERED: "Discovered",
  QUALIFYING: "Qualifying",
  QUALIFIED: "Qualified",
  REJECTED: "Rejected",
  SELECTED: "Selected",
  READY: "Ready",
  SUBMITTED: "Submitted",
  PUBLISHED: "Published",
  FAILED: "Failed",
  EXPIRED: "Expired",
};

export const OPPORTUNITY_TYPE_LABELS: Record<OpportunityType, string> = {
  FREE_DIRECTORY_LISTING: "Free directory listing",
  FREE_LOCAL_LISTING: "Free local listing",
  FREE_COMPANY_PROFILE: "Free company profile",
  FREE_STARTUP_LISTING: "Free startup listing",
  FREE_SOFTWARE_LISTING: "Free software listing",
  FREE_INDUSTRY_LISTING: "Free industry listing",
  FREE_ORGANIZATION_LISTING: "Free organization listing",
  FREE_PROFILE_LISTING: "Free profile listing",
};

export const SUBMISSION_STATUS_LABELS: Record<SubmissionStatus, string> = {
  READY: "Ready",
  IN_PROGRESS: "In progress",
  SUBMITTED: "Submitted",
  PENDING_APPROVAL: "Pending approval",
  PUBLISHED: "Published",
  VERIFICATION_PENDING: "Verification pending",
  VERIFIED: "Verified",
  REJECTED: "Rejected",
  FAILED: "Failed",
};

export const SUBMISSION_METHOD_LABELS: Record<SubmissionMethod, string> = {
  MANUAL: "Manual",
  FORM: "Web form",
  EMAIL: "Email",
  API: "API",
  ACCOUNT_REQUIRED: "Account required",
  UNKNOWN: "Unknown",
};

export const CONTENT_STATUS_LABELS: Record<ContentStatus, string> = {
  DRAFT: "Draft",
  PENDING_REVIEW: "Pending review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  SUPERSEDED: "Superseded",
};

export const CREDENTIAL_STATUS_LABELS: Record<CredentialStatus, string> = {
  CONFIGURED: "Configured",
  VERIFIED: "Verified",
  INVALID: "Invalid",
  DISABLED: "Disabled",
};

export const CREDENTIAL_PROVIDER_TYPE_LABELS: Record<CredentialProviderType, string> = {
  AI: "AI provider",
  SEARCH: "Search",
  SEO_METRICS: "SEO metrics",
  WEBSITE_INTELLIGENCE: "Website intelligence",
  OTHER: "Other",
};

export const MEMBERSHIP_STATUS_LABELS: Record<MembershipStatus, string> = {
  ACTIVE: "Active",
  INVITED: "Invited",
  SUSPENDED: "Suspended",
  REMOVED: "Removed",
};

export const TENANT_STATUS_LABELS: Record<TenantStatus, string> = {
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
  ARCHIVED: "Archived",
};

export const PRICING_TYPE_LABELS: Record<PricingType, string> = {
  FREE: "Free",
  PAID: "Paid",
  MIXED: "Mixed",
  UNKNOWN: "Unknown",
};

export const LINK_TYPE_LABELS: Record<LinkType, string> = {
  DOFOLLOW: "Dofollow",
  NOFOLLOW: "Nofollow",
  MIXED: "Mixed",
  UNKNOWN: "Unknown",
};

export const AI_PROVIDER_LABELS: Record<AiProvider, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  openrouter: "OpenRouter",
  custom: "Custom (OpenAI-compatible)",
};

export const AI_PURPOSE_LABELS: Record<AiPurpose, string> = {
  content_generation: "Content generation",
  discovery: "Publisher discovery",
  qualification: "Qualification",
  embedding: "Embeddings",
};

export const ROLE_SLUG_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  seo_manager: "SEO Manager",
  seo_specialist: "SEO Specialist",
  viewer: "Viewer",
};

/**
 * Fallback for any value the backend adds before the frontend is regenerated:
 * `PENDING_REVIEW` reads as "Pending review" rather than as a raw enum name.
 */
export function humanizeEnum(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .toLowerCase()
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word, index) => (index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(" ");
}

/** Look a label up, falling back to a humanised form of the raw value. */
export function labelFor(
  map: Record<string, string>,
  value: string | null | undefined,
): string {
  if (!value) return "—";
  return map[value] ?? humanizeEnum(value);
}

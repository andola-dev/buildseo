/**
 * Domain types, derived from the backend's OpenAPI document.
 *
 * `api.generated.ts` is produced by `npm run codegen:api` and must never be
 * edited by hand. Everything here is an alias into it, so a backend schema
 * change surfaces as a TypeScript error at every call site instead of drifting
 * silently. Nothing in the application imports `api.generated.ts` directly.
 */

import type { components } from "./api.generated";

type Schemas = components["schemas"];

/* -------------------------------------------------------------------------- */
/* Envelopes                                                                  */
/* -------------------------------------------------------------------------- */

export type UUID = string;
/** ISO-8601 timestamp string, as serialised by FastAPI. */
export type ISODateString = string;
/** ISO-8601 calendar date (no time component). */
export type ISODate = string;

/** Every successful single-resource response is `{ data, meta? }`. */
export interface ApiEnvelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export type PaginationMeta = Schemas["PaginationMeta"];

/** Every successful collection response is `{ data: T[], meta: PaginationMeta }`. */
export interface PaginatedEnvelope<T> {
  data: T[];
  meta: PaginationMeta;
}

/** Every failure response is `{ error: { code, message, details? } }`. */
export type ErrorDetail = Schemas["ErrorDetail"];
export type ErrorResponse = Schemas["ErrorResponse"];

/** Shared query parameters accepted by every collection endpoint. */
export interface PageParams {
  page?: number;
  page_size?: number;
  sort?: string | null;
  order?: "asc" | "desc";
}

/** A normalised field-level validation issue, flattened from a 422 response. */
export interface FieldIssue {
  field: string;
  message: string;
  code?: string;
}

/* -------------------------------------------------------------------------- */
/* Request-body defaults                                                      */
/* -------------------------------------------------------------------------- */

/**
 * A Pydantic field with a default is not listed in the schema's `required`
 * array, but `openapi-typescript` still emits it as required — correct for a
 * *response* (the server always sends it) and wrong for a *request* (the client
 * may omit it and let the server apply the default).
 *
 * `WithOptional` re-opens exactly those fields, so the request types below stay
 * generated-derived while remaining callable the way the API intends.
 */
type WithOptional<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

export type CampaignStatus = Schemas["CampaignStatus"];
export type ClientWebsiteStatus = Schemas["ClientWebsiteStatus"];
export type PublisherStatus = Schemas["PublisherStatus"];
export type PublisherCategory = Schemas["PublisherCategory"];
export type OpportunityStatus = Schemas["OpportunityStatus"];
export type OpportunityType = Schemas["OpportunityType"];
export type SubmissionStatus = Schemas["SubmissionStatus"];
export type SubmissionMethod = Schemas["SubmissionMethod"];
export type ContentStatus = Schemas["ContentStatus"];
export type CredentialStatus = Schemas["CredentialStatus"];
export type CredentialProviderType = Schemas["CredentialProviderType"];
export type MembershipStatus = Schemas["MembershipStatus"];
export type TenantStatus = Schemas["TenantStatus"];
export type PricingType = Schemas["PricingType"];
export type LinkType = Schemas["LinkType"];
export type AiProvider = Schemas["AiProvider"];
export type AiPurpose = Schemas["AiPurpose"];

/* -------------------------------------------------------------------------- */
/* Auth, identity and workspaces                                              */
/* -------------------------------------------------------------------------- */

export type User = Schemas["UserRead"];
export type UserUpdate = Schemas["UserUpdate"];
export type Me = Schemas["MeRead"];
export type TenantMembershipSummary = Schemas["TenantMembershipSummary"];
export type LoginRequest = Schemas["LoginRequest"];
export type RegisterRequest = Schemas["RegisterRequest"];
export type TokenPair = Schemas["TokenPair"];
export type AccessTokenResponse = Schemas["AccessTokenResponse"];
export type SelectTenantRequest = Schemas["SelectTenantRequest"];
export type PasswordChangeRequest = WithOptional<
  Schemas["PasswordChangeRequest"],
  "revoke_other_sessions"
>;
export type UserSession = Schemas["SessionRead"];

export type Tenant = Schemas["TenantRead"];
export type TenantCreate = Schemas["TenantCreate"];
export type TenantUpdate = Schemas["TenantUpdate"];

export type Membership = Schemas["MembershipRead"];
export type MembershipCreate = WithOptional<
  Schemas["MembershipCreate"],
  "role_slugs" | "status"
>;
export type MembershipUpdate = Schemas["MembershipUpdate"];

export type Role = Schemas["RoleRead"];
export type RoleCreate = Schemas["RoleCreate"];
export type RoleUpdate = Schemas["RoleUpdate"];
export type Permission = Schemas["PermissionRead"];

/* -------------------------------------------------------------------------- */
/* Client websites                                                            */
/* -------------------------------------------------------------------------- */

export type ClientWebsite = Schemas["ClientWebsiteRead"];
export type ClientWebsiteCreate = WithOptional<
  Schemas["ClientWebsiteCreate"],
  "status" | "target_countries"
>;
export type ClientWebsiteUpdate = Schemas["ClientWebsiteUpdate"];

export interface ClientWebsiteListParams extends PageParams {
  q?: string | null;
  status?: string | null;
  industry?: string | null;
  target_country?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Campaigns                                                                  */
/* -------------------------------------------------------------------------- */

export type Campaign = Schemas["CampaignRead"];
export type CampaignCreate = WithOptional<Schemas["CampaignCreate"], "status">;
export type CampaignUpdate = Schemas["CampaignUpdate"];
export type CampaignStats = Schemas["CampaignStats"];

export interface CampaignListParams extends PageParams {
  q?: string | null;
  status?: string | null;
  client_website_id?: string | null;
  target_country?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Publishers and discovery                                                   */
/* -------------------------------------------------------------------------- */

export type Publisher = Schemas["PublisherRead"];
export type PublisherCreate = WithOptional<
  Schemas["PublisherCreate"],
  "status" | "submission_method" | "pricing_type" | "link_type"
>;
export type PublisherUpdate = Schemas["PublisherUpdate"];
export type ScoreBreakdown = Schemas["ScoreBreakdown"];
export type QualificationRequest = Partial<Schemas["QualificationRequest"]>;
export type QualificationResult = Schemas["QualificationResult"];

export interface PublisherListParams extends PageParams {
  q?: string | null;
  status?: string | null;
  pricing_type?: string | null;
  category?: string | null;
  country?: string | null;
  language?: string | null;
  submission_method?: string | null;
  min_quality_score?: number | null;
  max_spam_score?: number | null;
  free_only?: boolean;
}

export type DiscoveryRequest = Partial<Schemas["DiscoveryRequest"]>;
export type DiscoveryRun = Schemas["DiscoveryRunRead"];
export type DiscoveryProvider = Schemas["DiscoveryProviderRead"];

export interface DiscoveryRunListParams extends PageParams {
  status?: string | null;
  provider?: string | null;
  campaign_id?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Opportunities and AI content                                               */
/* -------------------------------------------------------------------------- */

export type Opportunity = Schemas["OpportunityRead"];
export type OpportunityCreate = WithOptional<
  Schemas["OpportunityCreate"],
  "opportunity_type" | "priority"
>;
export type OpportunityUpdate = Schemas["OpportunityUpdate"];
export type OpportunityRejectRequest = Schemas["OpportunityRejectRequest"];
export type OpportunityTransitionRequest = Schemas["OpportunityTransitionRequest"];

export interface OpportunityListParams extends PageParams {
  q?: string | null;
  status?: string | null;
  campaign_id?: string | null;
  publisher_id?: string | null;
  opportunity_type?: string | null;
  category?: string | null;
  min_priority?: number | null;
  min_score?: number | null;
}

export type GeneratedContent = Schemas["GeneratedContentRead"];
export type ContentGenerationRequest = Partial<Schemas["ContentGenerationRequest"]>;
export type ContentReviewRequest = Schemas["ContentReviewRequest"];

/**
 * `GeneratedContentRead.generated_content` is an open object on the wire. This
 * is the shape the content generator actually produces; every field is
 * optional because the frontend must not assume the backend filled it.
 */
export interface GeneratedContentPayload {
  title?: string;
  short_description?: string;
  long_description?: string;
  description?: string;
  category?: string;
  tags?: string[];
  anchor_text?: string;
  [key: string]: unknown;
}

/* -------------------------------------------------------------------------- */
/* Submissions                                                                */
/* -------------------------------------------------------------------------- */

export type Submission = Schemas["SubmissionRead"];
export type SubmissionCreate = WithOptional<
  Schemas["SubmissionCreate"],
  "use_approved_content"
>;
export type SubmissionUpdate = Schemas["SubmissionUpdate"];
export type SubmissionApproveRequest = Schemas["SubmissionApproveRequest"];
export type SubmissionExecuteRequest = Partial<Schemas["SubmissionExecuteRequest"]>;
export type SubmissionVerifyRequest = Partial<Schemas["SubmissionVerifyRequest"]>;
export type SubmissionTransitionRequest = Schemas["SubmissionTransitionRequest"];
export type SubmissionStateMachine = Schemas["SubmissionStateMachineRead"];

export interface SubmissionListParams extends PageParams {
  q?: string | null;
  status?: string | null;
  campaign_id?: string | null;
  opportunity_id?: string | null;
  submission_method?: string | null;
}

/**
 * `SubmissionRead.verification_evidence` is an open object on the wire; this is
 * the shape the verification service writes into it.
 */
export interface VerificationEvidence {
  link_url?: string;
  anchor_text?: string;
  link_type?: string;
  http_status?: number;
  indexed?: boolean;
  found?: boolean;
  checked_at?: string;
  notes?: string;
  [key: string]: unknown;
}

/* -------------------------------------------------------------------------- */
/* Credentials (BYOK) and AI configuration                                    */
/* -------------------------------------------------------------------------- */

export type Credential = Schemas["CredentialRead"];
export type CredentialCreate = WithOptional<
  Schemas["CredentialCreate"],
  "provider_type" | "metadata" | "verify"
>;
export type CredentialUpdate = WithOptional<Schemas["CredentialUpdate"], "verify">;
export type CredentialVerifyResult = Schemas["CredentialVerifyResult"];

export interface CredentialListParams extends PageParams {
  provider?: string | null;
  provider_type?: string | null;
  status?: string | null;
}

export type AiConfig = Schemas["AiConfigRead"];
export type AiConfigUpsert = WithOptional<
  Schemas["AiConfigUpsert"],
  "parameters" | "is_default"
>;
export type AiUsage = Schemas["AiUsageRead"];
export type AiUsageSummary = Schemas["AiUsageSummary"];
export type AiUsageSummaryRow = Schemas["AiUsageSummaryRow"];

export interface AiUsageListParams extends PageParams {
  provider?: string | null;
  model?: string | null;
  operation?: string | null;
  status?: string | null;
  since?: string | null;
  until?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Audit and jobs                                                             */
/* -------------------------------------------------------------------------- */

export type AuditLog = Schemas["AuditLogRead"];

export interface AuditLogListParams extends PageParams {
  action?: string | null;
  user_id?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  since?: string | null;
  until?: string | null;
}

export type Job = Schemas["JobRead"];
export type JobAccepted = Schemas["JobAccepted"];

export interface JobListParams extends PageParams {
  status?: string | null;
  task_name?: string | null;
}

export type TenantMemberListParams = PageParams & { status?: string | null };
export type UserListParams = PageParams & { q?: string | null; status?: string | null };
export type RoleListParams = PageParams & { is_system?: boolean | null };

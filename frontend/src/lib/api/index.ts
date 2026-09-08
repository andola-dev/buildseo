/**
 * The API client surface.
 *
 * Feature code imports from here (or from a specific module) and never calls
 * `fetch` itself — ESLint enforces that outside `src/lib/api`.
 */

export { api, apiRequest, buildQuery, setSessionExpiredHandler } from "@/lib/api/http";
export {
  ApiError,
  isApiError,
  errorMessage,
  fieldErrorMap,
  ERROR_MESSAGES,
} from "@/lib/api/errors";
export { unwrap, unwrapPage, type Page } from "@/lib/api/envelope";
export {
  getAccessToken,
  clearAccessToken,
  subscribeToTokens,
} from "@/lib/api/token-store";

export * as authApi from "@/lib/api/auth";
export * as meApi from "@/lib/api/me";
export * as tenantsApi from "@/lib/api/tenants";
export * as usersApi from "@/lib/api/users";
export * as rolesApi from "@/lib/api/roles";
export * as websitesApi from "@/lib/api/websites";
export * as campaignsApi from "@/lib/api/campaigns";
export * as publishersApi from "@/lib/api/publishers";
export * as opportunitiesApi from "@/lib/api/opportunities";
export * as submissionsApi from "@/lib/api/submissions";
export * as credentialsApi from "@/lib/api/credentials";
export * as aiApi from "@/lib/api/ai";
export * as auditApi from "@/lib/api/audit";
export * as jobsApi from "@/lib/api/jobs";

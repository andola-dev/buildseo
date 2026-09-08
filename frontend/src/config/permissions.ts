/**
 * Permission codes recognised by the backend (app/rbac/catalog.py).
 *
 * These constants exist so a permission check is a typo-proof reference rather
 * than a loose string. They are used only to decide what the UI offers — the
 * FastAPI layer enforces authorization, and `/api/v1/permissions` remains the
 * source of truth for the role editor (spec §35).
 */

export const PERM = {
  TENANT_READ: "tenant.read",
  TENANT_UPDATE: "tenant.update",
  TENANT_DELETE: "tenant.delete",
  TENANT_TRANSFER_OWNERSHIP: "tenant.transfer_ownership",

  USER_READ: "user.read",
  USER_CREATE: "user.create",
  USER_UPDATE: "user.update",
  USER_DELETE: "user.delete",

  ROLE_READ: "role.read",
  ROLE_CREATE: "role.create",
  ROLE_UPDATE: "role.update",
  ROLE_DELETE: "role.delete",
  PERMISSION_READ: "permission.read",

  CLIENT_WEBSITE_READ: "client_website.read",
  CLIENT_WEBSITE_CREATE: "client_website.create",
  CLIENT_WEBSITE_UPDATE: "client_website.update",
  CLIENT_WEBSITE_DELETE: "client_website.delete",

  CAMPAIGN_READ: "campaign.read",
  CAMPAIGN_CREATE: "campaign.create",
  CAMPAIGN_UPDATE: "campaign.update",
  CAMPAIGN_DELETE: "campaign.delete",

  PUBLISHER_READ: "publisher.read",
  PUBLISHER_CREATE: "publisher.create",
  PUBLISHER_UPDATE: "publisher.update",
  PUBLISHER_DELETE: "publisher.delete",
  PUBLISHER_DISCOVER: "publisher.discover",
  PUBLISHER_QUALIFY: "publisher.qualify",

  OPPORTUNITY_READ: "opportunity.read",
  OPPORTUNITY_CREATE: "opportunity.create",
  OPPORTUNITY_UPDATE: "opportunity.update",
  OPPORTUNITY_DELETE: "opportunity.delete",

  SUBMISSION_READ: "submission.read",
  SUBMISSION_CREATE: "submission.create",
  SUBMISSION_UPDATE: "submission.update",
  SUBMISSION_DELETE: "submission.delete",
  SUBMISSION_APPROVE: "submission.approve",
  SUBMISSION_VERIFY: "submission.verify",

  CREDENTIAL_READ: "credential.read",
  CREDENTIAL_CREATE: "credential.create",
  CREDENTIAL_UPDATE: "credential.update",
  CREDENTIAL_DELETE: "credential.delete",

  INTEGRATION_READ: "integration.read",
  INTEGRATION_CREATE: "integration.create",
  INTEGRATION_UPDATE: "integration.update",
  INTEGRATION_DELETE: "integration.delete",
  AI_GENERATE: "ai.generate",
  AI_USAGE_READ: "ai.usage_read",

  AUDIT_READ: "audit.read",
  JOB_READ: "job.read",
  JOB_CREATE: "job.create",
} as const;

export type PermissionCode = (typeof PERM)[keyof typeof PERM];

/** Display names for the resource groups shown in the role editor. */
export const RESOURCE_LABELS: Record<string, string> = {
  tenant: "Workspace",
  user: "Members",
  role: "Roles",
  permission: "Permissions",
  client_website: "Client websites",
  campaign: "Campaigns",
  publisher: "Publishers",
  opportunity: "Opportunities",
  submission: "Submissions",
  credential: "Credentials",
  integration: "Integrations",
  ai: "AI",
  audit: "Audit",
  job: "Jobs",
};

export const ACTION_LABELS: Record<string, string> = {
  read: "View",
  create: "Create",
  update: "Update",
  delete: "Delete",
  approve: "Approve",
  verify: "Verify",
  discover: "Discover",
  qualify: "Qualify",
  generate: "Generate",
  usage_read: "View usage",
  transfer_ownership: "Transfer ownership",
};

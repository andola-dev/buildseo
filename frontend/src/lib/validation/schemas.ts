/**
 * Client-side validation schemas (spec §41).
 *
 * These catch mistakes before a request is made; the backend's Pydantic models
 * remain authoritative and its 422 responses are mapped back onto the same
 * fields by `fieldErrorMap`.
 */

import { z } from "zod";

/** Mirrors the backend's `PASSWORD_MIN_LENGTH` default. */
export const PASSWORD_MIN_LENGTH = 12;

export const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Enter your email address.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
  remember: z.boolean(),
});

export type LoginValues = z.infer<typeof loginSchema>;

/**
 * A website URL.
 *
 * The backend normalises the domain itself, so a bare host is accepted here and
 * given a scheme before submission rather than rejected.
 */
export const websiteUrlSchema = z
  .string()
  .min(1, "Enter the website URL.")
  .transform((value) => value.trim())
  .refine(
    (value) => {
      const candidate = /^https?:\/\//i.test(value) ? value : `https://${value}`;
      try {
        const url = new URL(candidate);
        return url.hostname.includes(".");
      } catch {
        return false;
      }
    },
    { message: "Enter a valid website URL, e.g. example.com" },
  );

/** Add a scheme if the user typed a bare host. */
export function normalizeUrl(value: string): string {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

export const clientWebsiteSchema = z.object({
  name: z.string().min(2, "Enter a name of at least 2 characters.").max(200),
  website_url: websiteUrlSchema,
  description: z.string().max(2000).optional().or(z.literal("")),
  industry: z.string().max(120).optional().or(z.literal("")),
  target_country: z.string().max(2).optional().or(z.literal("")),
  target_language: z.string().max(10).optional().or(z.literal("")),
});

export type ClientWebsiteValues = z.infer<typeof clientWebsiteSchema>;

export const campaignSchema = z.object({
  client_website_id: z.string().min(1, "Select a client website."),
  name: z.string().min(2, "Enter a campaign name of at least 2 characters.").max(200),
  description: z.string().max(2000).optional().or(z.literal("")),
  target_country: z.string().max(2).optional().or(z.literal("")),
  target_language: z.string().max(10).optional().or(z.literal("")),
  target_link_count: z
    .number({ message: "Enter a number." })
    .int("Enter a whole number.")
    .min(1, "Target at least 1 link.")
    .max(100000, "That target is unrealistically high.")
    .nullable(),
  start_date: z.string().optional().or(z.literal("")),
  end_date: z.string().optional().or(z.literal("")),
});

export type CampaignValues = z.infer<typeof campaignSchema>;

export const publisherSchema = z.object({
  website_url: websiteUrlSchema,
  name: z.string().max(200).optional().or(z.literal("")),
  description: z.string().max(2000).optional().or(z.literal("")),
  category: z.string().optional().or(z.literal("")),
  country: z.string().max(2).optional().or(z.literal("")),
  language: z.string().max(10).optional().or(z.literal("")),
  submission_url: z.string().optional().or(z.literal("")),
  submission_method: z.string().optional().or(z.literal("")),
});

export type PublisherValues = z.infer<typeof publisherSchema>;

export const discoverySchema = z.object({
  provider: z.string().min(1, "Choose a discovery provider."),
  keywords: z.string().min(2, "Enter at least one keyword."),
  country: z.string().max(2).optional().or(z.literal("")),
  language: z.string().max(10).optional().or(z.literal("")),
  category: z.string().optional().or(z.literal("")),
  campaign_id: z.string().optional().or(z.literal("")),
  limit: z.number().int().min(1).max(200),
});

export type DiscoveryValues = z.infer<typeof discoverySchema>;

export const submissionContentSchema = z.object({
  submitted_title: z
    .string()
    .min(3, "Enter a title of at least 3 characters.")
    .max(300)
    .nullable(),
  submitted_description: z.string().max(5000).nullable(),
  anchor_text: z.string().max(300).nullable(),
  notes: z.string().max(2000).nullable(),
});

export type SubmissionContentValues = z.infer<typeof submissionContentSchema>;

export const credentialSchema = z.object({
  provider: z.string().min(1, "Choose a provider."),
  label: z.string().min(2, "Enter a label so you can recognise this key.").max(120),
  secret: z.string().min(8, "That key looks too short."),
  verify: z.boolean(),
});

export type CredentialValues = z.infer<typeof credentialSchema>;

export const workspaceSchema = z.object({
  name: z.string().min(2, "Enter a workspace name of at least 2 characters.").max(200),
  slug: z
    .string()
    .regex(/^[a-z0-9-]*$/, "Use lowercase letters, numbers and hyphens only.")
    .max(80)
    .optional()
    .or(z.literal("")),
});

export type WorkspaceValues = z.infer<typeof workspaceSchema>;

export const roleSchema = z.object({
  slug: z
    .string()
    .min(2, "Enter a slug of at least 2 characters.")
    .max(80)
    .regex(/^[a-z0-9_-]+$/, "Use lowercase letters, numbers, hyphens and underscores."),
  name: z.string().min(2, "Enter a role name.").max(120),
  description: z.string().max(500).optional().or(z.literal("")),
  permissions: z.array(z.string()).min(1, "Grant at least one permission."),
});

export type RoleValues = z.infer<typeof roleSchema>;

export const profileSchema = z.object({
  first_name: z.string().max(120).optional().or(z.literal("")),
  last_name: z.string().max(120).optional().or(z.literal("")),
});

export type ProfileValues = z.infer<typeof profileSchema>;

export const passwordChangeSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: z
      .string()
      .min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters.`),
    confirm_password: z.string().min(1, "Confirm your new password."),
    revoke_other_sessions: z.boolean(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "The passwords don't match.",
    path: ["confirm_password"],
  });

export type PasswordChangeValues = z.infer<typeof passwordChangeSchema>;

export const memberInviteSchema = z.object({
  email: z.string().min(1, "Enter an email address.").email("Enter a valid email address."),
  role_slugs: z.array(z.string()).min(1, "Assign at least one role."),
});

export type MemberInviteValues = z.infer<typeof memberInviteSchema>;

/** Turn a comma/newline separated field into a clean list. */
export function parseKeywords(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((keyword) => keyword.trim())
    .filter(Boolean);
}

/** Drop empty-string optionals so they are omitted rather than sent as "". */
export function omitEmpty<T extends Record<string, unknown>>(values: T): Partial<T> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === "" || value === undefined) continue;
    result[key] = value;
  }
  return result as Partial<T>;
}

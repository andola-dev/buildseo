import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SubmissionDetail } from "@/features/submissions/components/submission-detail";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import { jsonResponse, renderWithQuery, TENANT_A } from "@/test/utils";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/submissions/sub-1",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/tenant/use-tenant", () => ({
  useTenant: () => ({
    tenants: [],
    activeTenantId: TENANT_A,
    activeTenant: null,
    tenantVersion: 0,
    switchingTenant: false,
    switchTenant: vi.fn(),
  }),
  useTenantId: () => TENANT_A,
}));

/** Grants every permission, so these tests exercise workflow, not RBAC. */
const granted = new Set<string>(["*"]);
vi.mock("@/lib/permissions/use-permissions", () => ({
  usePermissions: () => ({
    permissions: granted,
    can: () => granted.has("*"),
    canAny: () => granted.has("*"),
    canAll: () => granted.has("*"),
  }),
  matchesPermission: () => granted.has("*"),
}));

function makeSubmission(overrides: Record<string, unknown> = {}) {
  return {
    id: "sub-1",
    campaign_id: "camp-1",
    opportunity_id: "opp-1",
    status: "PENDING_APPROVAL",
    submitted_url: null,
    target_url: "https://acme.com/pricing",
    anchor_text: "Acme pricing",
    submitted_title: "Acme — B2B SaaS",
    submitted_description: "Acme helps teams ship faster.",
    submission_method: "FORM",
    approved_by_user_id: null,
    approved_at: null,
    submitted_at: null,
    published_at: null,
    verified_at: null,
    failure_reason: null,
    notes: null,
    verification_evidence: {},
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-01T09:00:00Z",
    ...overrides,
  };
}

/** Stub every request the detail page makes, with a controllable submission. */
function stubApi(getSubmission: () => Record<string, unknown>, onPost?: (url: string) => void) {
  globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);

    if (init?.method === "POST") {
      onPost?.(url);
      return jsonResponse({ data: getSubmission() });
    }

    if (/\/submissions\/sub-1$/.test(url)) {
      return jsonResponse({ data: getSubmission() });
    }
    if (/\/opportunities\/opp-1$/.test(url)) {
      return jsonResponse({
        data: {
          id: "opp-1",
          campaign_id: "camp-1",
          publisher_id: "pub-1",
          opportunity_type: "FREE_DIRECTORY_LISTING",
          target_url: "https://acme.com/pricing",
          category: "SOFTWARE_DIRECTORY",
          status: "READY",
          priority: 50,
          created_at: "2026-09-01T09:00:00Z",
          updated_at: "2026-09-01T09:00:00Z",
        },
      });
    }
    if (/\/publishers\/pub-1$/.test(url)) {
      return jsonResponse({
        data: {
          id: "pub-1",
          domain: "saas-directory.com",
          normalized_domain: "saas-directory.com",
          website_url: "https://saas-directory.com",
          name: "SaaS Directory",
          submission_url: "https://saas-directory.com/submit",
          submission_method: "FORM",
          pricing_type: "FREE",
          link_type: "DOFOLLOW",
          status: "QUALIFIED",
          is_submittable: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      });
    }
    if (/\/campaigns\/camp-1$/.test(url)) {
      return jsonResponse({
        data: {
          id: "camp-1",
          client_website_id: "web-1",
          name: "SaaS Directory Campaign",
          status: "ACTIVE",
          free_only: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      });
    }

    return jsonResponse({ data: null });
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  setAccessToken({ accessToken: "tok", expiresIn: 900 });
});

describe("SubmissionDetail", () => {
  it("renders the listing content and the publisher", async () => {
    stubApi(() => makeSubmission());
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    // The title appears both as the page heading and in the content panel, so
    // the heading is queried by role to keep the assertion unambiguous.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Acme — B2B SaaS" }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("Acme helps teams ship faster.")).toBeInTheDocument();
    // The status shows in the header badge and in the progress timeline.
    expect(screen.getAllByText("Pending approval").length).toBeGreaterThan(0);
  });

  it("offers approve and reject while the submission awaits a decision", async () => {
    stubApi(() => makeSubmission());
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
  });

  it("calls the approve endpoint", async () => {
    const posts: string[] = [];
    stubApi(() => makeSubmission(), (url) => posts.push(url));

    const user = userEvent.setup();
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() =>
      expect(posts.some((url) => url.endsWith("/submissions/sub-1/approve"))).toBe(true),
    );
  });

  it("requires a reason before rejecting", async () => {
    const posts: string[] = [];
    stubApi(() => makeSubmission(), (url) => posts.push(url));

    const user = userEvent.setup();
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    // Submit from inside the dialog: the page header carries a Reject button
    // of its own, so the query has to be scoped.
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^reject$/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Give a short reason so the decision is auditable."),
      ).toBeInTheDocument(),
    );
    expect(posts.some((url) => url.includes("/transition"))).toBe(false);
  });

  it("links out to the publisher's own form rather than automating it", async () => {
    stubApi(() => makeSubmission({ status: "READY" }));
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /open publisher/i })).toBeInTheDocument(),
    );

    const link = screen.getByRole("link", { name: /open publisher/i });
    expect(link).toHaveAttribute("href", "https://saas-directory.com/submit");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));

    // The user records completion themselves; nothing submits the form for them.
    expect(
      screen.getByRole("button", { name: /submission complete/i }),
    ).toBeInTheDocument();
  });

  it("shows the verification result once the backend has checked the link", async () => {
    stubApi(() =>
      makeSubmission({
        status: "VERIFIED",
        verified_at: "2026-09-05T12:00:00Z",
        submitted_url: "https://saas-directory.com/listing/acme",
        verification_evidence: {
          link_url: "https://saas-directory.com/listing/acme",
          anchor_text: "Acme pricing",
          link_type: "dofollow",
          http_status: 200,
          found: true,
          indexed: true,
        },
      }),
    );

    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    // "Verified" legitimately appears in the status badge, the timeline and the
    // details list, so the assertion is on the evidence values instead.
    await waitFor(() => expect(screen.getByText("dofollow")).toBeInTheDocument());
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: /saas-directory.com\/listing\/acme/ }),
    ).toBeInTheDocument();
  });

  it("says verification hasn't run when there is no evidence", async () => {
    stubApi(() => makeSubmission({ status: "SUBMITTED" }));
    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(
        screen.getByText(/Not verified yet/),
      ).toBeInTheDocument(),
    );
  });

  it("shows the failure reason for a failed submission", async () => {
    stubApi(() =>
      makeSubmission({ status: "FAILED", failure_reason: "The directory rejected the listing." }),
    );

    renderWithQuery(<SubmissionDetail submissionId="sub-1" />);

    await waitFor(() =>
      expect(screen.getByText("The directory rejected the listing.")).toBeInTheDocument(),
    );
    expect(screen.getByText("Submission failed")).toBeInTheDocument();
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CampaignWizard } from "@/features/campaigns/components/campaign-wizard";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import {
  jsonResponse,
  makeMeta,
  renderWithQuery,
  TENANT_A,
} from "@/test/utils";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/campaigns/new",
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

const WEBSITE = {
  id: "web-1",
  name: "Acme SaaS",
  domain: "acme.com",
  normalized_domain: "acme.com",
  website_url: "https://acme.com",
  description: null,
  industry: "B2B software",
  target_country: "US",
  target_countries: [],
  target_language: "en",
  status: "ACTIVE",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  push.mockClear();
  setAccessToken({ accessToken: "tok", expiresIn: 900 });
});

/** Advance through the wizard to the review step. */
async function completeSteps(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("radio", { name: /Acme SaaS/ }));
  await user.click(screen.getByRole("button", { name: /continue/i }));

  await user.type(
    screen.getByLabelText(/campaign name/i),
    "SaaS Directory Campaign",
  );
  await user.click(screen.getByRole("button", { name: /continue/i }));

  await user.type(screen.getByLabelText(/target country/i), "us");
  await user.click(screen.getByRole("button", { name: /continue/i }));

  await user.type(screen.getByLabelText(/target link count/i), "250");
  await user.click(screen.getByRole("button", { name: /continue/i }));
}

describe("CampaignWizard", () => {
  it("tells the user to add a website first rather than showing an empty picker", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ data: [], meta: makeMeta({ total: 0 }) }),
    ) as unknown as typeof fetch;

    renderWithQuery(<CampaignWizard />);

    await waitFor(() =>
      expect(screen.getByText("Add a client website first")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /add client website/i }),
    ).toBeInTheDocument();
  });

  it("blocks Continue until the required field for the step is filled", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ data: [WEBSITE], meta: makeMeta() }),
    ) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<CampaignWizard />);

    await waitFor(() => expect(screen.getByText("Acme SaaS")).toBeInTheDocument());

    // Step 1 needs a website selected.
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: /Acme SaaS/ }));
    expect(screen.getByRole("button", { name: /continue/i })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Step 2 needs a name.
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("states the free-listings-only scope on the link requirements step", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ data: [WEBSITE], meta: makeMeta() }),
    ) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<CampaignWizard />);
    await waitFor(() => expect(screen.getByText("Acme SaaS")).toBeInTheDocument());

    await user.click(screen.getByRole("radio", { name: /Acme SaaS/ }));
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.type(screen.getByLabelText(/campaign name/i), "Q4");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByText("Link type")).toBeInTheDocument();
    expect(screen.getByText("Free listings only")).toBeInTheDocument();

    // The scope is stated, not offered as a choice: there is no control for
    // link type and nothing selectable that mentions paid placement (spec §73).
    expect(screen.queryByRole("combobox", { name: /link type/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /paid/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /paid/i })).not.toBeInTheDocument();
  });

  it("creates the campaign from the review step and navigates to it", async () => {
    const posts: unknown[] = [];

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);

      if (init?.method === "POST" && url.endsWith("/campaigns")) {
        posts.push(JSON.parse(String(init.body)));
        return jsonResponse({ data: { id: "camp-9", name: "SaaS Directory Campaign" } });
      }

      return jsonResponse({ data: [WEBSITE], meta: makeMeta() });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<CampaignWizard />);
    await waitFor(() => expect(screen.getByText("Acme SaaS")).toBeInTheDocument());

    await completeSteps(user);

    // The review step summarises what will be created.
    expect(
      screen.getByRole("button", { name: /create campaign/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("SaaS Directory Campaign")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /create campaign/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/campaigns/camp-9"));

    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({
      client_website_id: "web-1",
      name: "SaaS Directory Campaign",
      target_link_count: 250,
      target_country: "US",
    });
  });

  it("surfaces a backend validation error on the field it belongs to", async () => {
    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);

      if (init?.method === "POST" && url.endsWith("/campaigns")) {
        return jsonResponse(
          {
            detail: [
              { loc: ["body", "name"], msg: "A campaign with that name exists", type: "value_error" },
            ],
          },
          422,
        );
      }

      return jsonResponse({ data: [WEBSITE], meta: makeMeta() });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<CampaignWizard />);
    await waitFor(() => expect(screen.getByText("Acme SaaS")).toBeInTheDocument());

    await completeSteps(user);
    await user.click(screen.getByRole("button", { name: /create campaign/i }));

    // The wizard returns to the step that owns the field so the message is visible.
    await waitFor(() =>
      expect(screen.getByText("A campaign with that name exists")).toBeInTheDocument(),
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("rejects an end date before the start date without calling the API", async () => {
    let posted = false;

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (init?.method === "POST" && String(input).endsWith("/campaigns")) posted = true;
      return jsonResponse({ data: [WEBSITE], meta: makeMeta() });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<CampaignWizard />);
    await waitFor(() => expect(screen.getByText("Acme SaaS")).toBeInTheDocument());

    await user.click(screen.getByRole("radio", { name: /Acme SaaS/ }));
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.type(screen.getByLabelText(/campaign name/i), "Q4");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await user.type(screen.getByLabelText(/start date/i), "2026-12-01");
    await user.type(screen.getByLabelText(/end date/i), "2026-01-01");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /create campaign/i }));

    await waitFor(() =>
      expect(
        screen.getByText("The end date can't be before the start date."),
      ).toBeInTheDocument(),
    );
    expect(posted).toBe(false);
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PublishersTable } from "@/features/publishers/components/publishers-table";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import { jsonResponse, makeMeta, renderWithQuery, TENANT_A } from "@/test/utils";

const push = vi.fn();
const setParams = vi.fn();

/** The URL is the single source of table state, so it is stubbed here. */
let params = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/publishers",
  useSearchParams: () => params,
}));

vi.mock("@/hooks/use-url-state", () => ({
  useUrlState: () => ({
    get: (key: string) => params.get(key),
    getNumber: (key: string, fallback: number) => {
      const raw = params.get(key);
      const parsed = raw === null ? Number.NaN : Number.parseInt(raw, 10);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    },
    getBoolean: (key: string) => params.get(key) === "true",
    setParams,
    clearParams: (keys: readonly string[]) => setParams(Object.fromEntries(keys.map((k) => [k, null]))),
    activeCount: (keys: readonly string[]) =>
      keys.filter((key) => {
        const value = params.get(key);
        return value !== null && value !== "";
      }).length,
    searchParams: params,
  }),
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

const granted = new Set<string>(["*"]);
vi.mock("@/lib/permissions/use-permissions", () => ({
  usePermissions: () => ({
    permissions: granted,
    can: () => true,
    canAny: () => true,
    canAll: () => true,
  }),
  matchesPermission: () => true,
}));

function makePublisher(overrides: Record<string, unknown> = {}) {
  return {
    id: "pub-1",
    domain: "saas-directory.com",
    normalized_domain: "saas-directory.com",
    website_url: "https://saas-directory.com",
    name: "SaaS Directory",
    description: null,
    category: "SOFTWARE_DIRECTORY",
    country: "US",
    language: "en",
    submission_url: "https://saas-directory.com/submit",
    contact_url: null,
    submission_method: "FORM",
    pricing_type: "FREE",
    link_type: "DOFOLLOW",
    dofollow_supported: true,
    nofollow_supported: false,
    status: "QUALIFIED",
    quality_score: 82,
    relevance_score: 74,
    spam_score: 8,
    authority_score: 55,
    organic_traffic: 42_000,
    signals: {},
    is_submittable: true,
    discovery_run_id: null,
    last_checked_at: "2026-09-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

/** Record every publisher-list request so query params can be asserted. */
function stubList(items: Record<string, unknown>[], total = items.length) {
  const requests: string[] = [];

  globalThis.fetch = vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url.includes("/publishers")) {
      requests.push(url);
      return jsonResponse({ data: items, meta: makeMeta({ total, total_pages: 1 }) });
    }
    return jsonResponse({ data: [], meta: makeMeta({ total: 0 }) });
  }) as unknown as typeof fetch;

  return requests;
}

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  params = new URLSearchParams();
  push.mockClear();
  setParams.mockClear();
  setAccessToken({ accessToken: "tok", expiresIn: 900 });
});

describe("PublishersTable", () => {
  it("renders publisher rows with their scores", async () => {
    stubList([makePublisher()]);
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(screen.getByText("SaaS Directory")).toBeInTheDocument());

    expect(screen.getAllByText("saas-directory.com").length).toBeGreaterThan(0);
    expect(screen.getByText("82")).toBeInTheDocument(); // quality
    expect(screen.getByText("8")).toBeInTheDocument(); // spam
    expect(screen.getByText("42K")).toBeInTheDocument(); // traffic
    expect(screen.getByText("Qualified")).toBeInTheDocument();
  });

  it("requests free inventory only, so paid publishers are never fetched", async () => {
    const requests = stubList([makePublisher()]);
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(requests.length).toBeGreaterThan(0));

    // The MVP scope is enforced in the request, not just hidden in the UI.
    expect(requests[0]).toContain("pricing_type=FREE");
    expect(requests[0]).toContain("free_only=true");
  });

  it("sends server-side pagination parameters rather than fetching everything", async () => {
    const requests = stubList([makePublisher()]);
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(requests.length).toBeGreaterThan(0));

    expect(requests[0]).toContain("page=1");
    expect(requests[0]).toContain("page_size=25");
  });

  it("reads its filters from the URL and forwards them to the API", async () => {
    params = new URLSearchParams({
      status: "REJECTED",
      country: "GB",
      min_quality_score: "60",
      q: "directory",
    });

    const requests = stubList([]);
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(requests.length).toBeGreaterThan(0));

    const url = requests[0]!;
    expect(url).toContain("status=REJECTED");
    expect(url).toContain("country=GB");
    expect(url).toContain("min_quality_score=60");
    expect(url).toContain("q=directory");
  });

  it("writes a filter change to the URL rather than to local state", async () => {
    stubList([makePublisher()]);
    const user = userEvent.setup();
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(screen.getByText("SaaS Directory")).toBeInTheDocument());

    // The column header also carries "Status"; the filter trigger's accessible
    // name includes its current value.
    await user.click(screen.getByRole("button", { name: "StatusAny" }));
    await user.click(await screen.findByRole("menuitem", { name: "Rejected" }));

    expect(setParams).toHaveBeenCalledWith({ status: "REJECTED" });
  });

  it("offers a filter-specific empty state when filters are active", async () => {
    params = new URLSearchParams({ status: "BLOCKED" });
    stubList([], 0);

    renderWithQuery(<PublishersTable />);

    await waitFor(() =>
      expect(screen.getByText("No publishers match these filters")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /clear filters/i })).toBeInTheDocument();
  });

  it("points an empty database at discovery instead of saying 'no data'", async () => {
    stubList([], 0);
    renderWithQuery(<PublishersTable />);

    await waitFor(() =>
      expect(screen.getByText("No publishers yet")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /start discovery/i })).toBeInTheDocument();
  });

  it("navigates to the publisher on row click", async () => {
    stubList([makePublisher()]);
    const user = userEvent.setup();
    renderWithQuery(<PublishersTable />);

    await waitFor(() => expect(screen.getByText("SaaS Directory")).toBeInTheDocument());

    await user.click(screen.getByText("Qualified"));
    expect(push).toHaveBeenCalledWith("/publishers/pub-1");
  });
});

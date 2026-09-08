import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CredentialDialog } from "@/features/credentials/components/credential-dialog";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import { jsonResponse, renderWithQuery, TENANT_A } from "@/test/utils";

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

const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
];

const SECRET = "sk-live-0123456789abcdefghij";

const READ_MODEL = {
  id: "cred-1",
  provider: "openai",
  provider_type: "AI",
  label: "Production key",
  status: "VERIFIED",
  masked_key: "••••••••hij",
  metadata: {},
  key_version: 1,
  last_verified_at: "2026-09-01T00:00:00Z",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  setAccessToken({ accessToken: "tok", expiresIn: 900 });
});

describe("CredentialDialog secret handling", () => {
  it("posts the key once and never writes it to browser storage", async () => {
    const bodies: string[] = [];

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (typeof init?.body === "string") bodies.push(init.body);
      const url = String(input);
      if (url.endsWith("/credentials") && init?.method === "POST") {
        return jsonResponse({ data: READ_MODEL });
      }
      return jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } });
    }) as unknown as typeof fetch;

    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={onOpenChange}
        providerType="AI"
        providers={PROVIDERS}
      />,
    );

    await user.type(screen.getByLabelText(/label/i), "Production key");
    await user.type(screen.getByLabelText(/api key/i), SECRET);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));

    // Sent exactly once, to the credentials endpoint.
    const withSecret = bodies.filter((body) => body.includes(SECRET));
    expect(withSecret).toHaveLength(1);
    expect(JSON.parse(withSecret[0]!)).toMatchObject({
      provider: "openai",
      provider_type: "AI",
      label: "Production key",
      secret: SECRET,
    });

    // Never persisted anywhere a script could read it later.
    const storage = JSON.stringify({
      local: { ...window.localStorage },
      session: { ...window.sessionStorage },
    });
    expect(storage).not.toContain(SECRET);
    expect(document.cookie).not.toContain(SECRET);
  });

  it("clears the key from the form after a successful submit", async () => {
    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (String(input).endsWith("/credentials") && init?.method === "POST") {
        return jsonResponse({ data: READ_MODEL });
      }
      return jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={() => {}}
        providerType="AI"
        providers={PROVIDERS}
      />,
    );

    const keyField = screen.getByLabelText(/api key/i);
    await user.type(screen.getByLabelText(/label/i), "Production key");
    await user.type(keyField, SECRET);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    await waitFor(() => expect(keyField).toHaveValue(""));
  });

  it("clears the key even when the request fails, so it does not linger in state", async () => {
    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (String(input).endsWith("/credentials") && init?.method === "POST") {
        return jsonResponse(
          { error: { code: "CREDENTIAL_ERROR", message: "The provider rejected the key." } },
          422,
        );
      }
      return jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={() => {}}
        providerType="AI"
        providers={PROVIDERS}
      />,
    );

    const keyField = screen.getByLabelText(/api key/i);
    await user.type(screen.getByLabelText(/label/i), "Production key");
    await user.type(keyField, SECRET);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    await waitFor(() =>
      expect(screen.getByText("We couldn't use that credential.")).toBeInTheDocument(),
    );
    expect(keyField).toHaveValue("");
  });

  it("uses a password field and opts out of autofill for the key", () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } }),
    ) as unknown as typeof fetch;

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={() => {}}
        providerType="AI"
        providers={PROVIDERS}
      />,
    );

    const keyField = screen.getByLabelText(/api key/i);
    expect(keyField).toHaveAttribute("type", "password");
    expect(keyField).toHaveAttribute("autocomplete", "off");
    expect(keyField).toHaveAttribute("data-lpignore", "true");
  });

  it("rejects an implausibly short key before making a request", async () => {
    let posted = false;

    globalThis.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (String(input).endsWith("/credentials") && init?.method === "POST") posted = true;
      return jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={() => {}}
        providerType="AI"
        providers={PROVIDERS}
      />,
    );

    await user.type(screen.getByLabelText(/label/i), "Prod");
    await user.type(screen.getByLabelText(/api key/i), "short");
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    await waitFor(() =>
      expect(screen.getByText("That key looks too short.")).toBeInTheDocument(),
    );
    expect(posted).toBe(false);
  });

  it("explains how the key is handled, and never shows a stored key", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ data: [], meta: { page: 1, page_size: 25, total: 0, total_pages: 0, has_next: false, has_previous: false } }),
    ) as unknown as typeof fetch;

    renderWithQuery(
      <CredentialDialog
        open
        onOpenChange={() => {}}
        providerType="AI"
        providers={PROVIDERS}
        credential={READ_MODEL}
      />,
    );

    expect(screen.getByText("How your key is handled")).toBeInTheDocument();

    // Rotating shows the label but starts with an empty key field: the stored
    // key is not readable, only replaceable.
    expect(screen.getByLabelText(/label/i)).toHaveValue("Production key");
    expect(screen.getByLabelText(/api key/i)).toHaveValue("");
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RegisterForm } from "@/features/auth/components/register-form";
import { __resetTransportState } from "@/lib/api/http";
import { clearAccessToken, getAccessToken } from "@/lib/api/token-store";
import { jsonResponse, renderWithQuery } from "@/test/utils";

const assign = vi.fn();

beforeEach(() => {
  clearAccessToken();
  __resetTransportState();
  assign.mockClear();
  Object.defineProperty(window, "location", {
    writable: true,
    value: { assign, pathname: "/register", search: "" },
  });
});

const PASSWORD = "a-sufficiently-long-password";

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/workspace name/i), "Acme Marketing");
  await user.type(screen.getByLabelText(/^email/i), "new@example.com");
  await user.type(screen.getByLabelText(/^password/i), PASSWORD);
  await user.type(screen.getByLabelText(/confirm password/i), PASSWORD);
}

describe("RegisterForm", () => {
  it("registers through the session proxy, never straight to FastAPI", async () => {
    const calls: string[] = [];

    globalThis.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      calls.push(url);
      if (url === "/api/session/register") {
        return jsonResponse({
          access_token: "new-token",
          expires_in: 900,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
          active_tenant_id: "tenant-1",
        });
      }
      throw new Error(`unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/dashboard"));

    // Only the same-origin session route is contacted; the refresh token is
    // captured server-side into an HTTP-only cookie.
    expect(calls).toEqual(["/api/session/register"]);
    expect(getAccessToken()).toBe("new-token");
  });

  it("sends the workspace name, so the account is usable on arrival", async () => {
    let sent: Record<string, unknown> = {};

    globalThis.fetch = vi.fn(async (_input: unknown, init?: RequestInit) => {
      sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return jsonResponse({ access_token: "t", expires_in: 900 });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() => expect(sent.email).toBe("new@example.com"));
    expect(sent.tenant_name).toBe("Acme Marketing");
  });

  it("does not leave the password in the DOM after submitting", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ access_token: "t", expires_in: 900 }),
    ) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(screen.getByLabelText(/^password/i)).toHaveValue(""),
    );
    expect(screen.getByLabelText(/confirm password/i)).toHaveValue("");
  });

  it("rejects mismatched passwords on the confirm field, before any request", async () => {
    let requested = false;
    globalThis.fetch = vi.fn(async () => {
      requested = true;
      return jsonResponse({});
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await user.type(screen.getByLabelText(/workspace name/i), "Acme");
    await user.type(screen.getByLabelText(/^email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), PASSWORD);
    await user.type(screen.getByLabelText(/confirm password/i), "something-else-entirely");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(screen.getByText("The passwords don't match.")).toBeInTheDocument(),
    );
    expect(requested).toBe(false);
  });

  it("enforces the backend's minimum password length locally", async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse({})) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await user.type(screen.getByLabelText(/workspace name/i), "Acme");
    await user.type(screen.getByLabelText(/^email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument(),
    );
  });

  it("maps a duplicate-account error onto the email field", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(
        {
          error: {
            code: "DUPLICATE_RESOURCE",
            message: "An account with that email already exists",
            details: { fields: { email: "An account with that email already exists" } },
          },
        },
        409,
      ),
    ) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(
        screen.getByText("An account with that email already exists"),
      ).toBeInTheDocument(),
    );
    expect(assign).not.toHaveBeenCalled();
  });

  it("reports an unreachable server distinctly from a rejected registration", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithQuery(<RegisterForm />);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(screen.getByText("Can't reach the server")).toBeInTheDocument(),
    );
  });
});

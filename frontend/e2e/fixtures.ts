import { test as base, expect, type Page } from "@playwright/test";

/**
 * E2E credentials.
 *
 * These specs run against a **real backend** — nothing here is mocked, because
 * a suite that asserts against a fake API proves nothing about the contract
 * (spec §70). When the environment is not configured the specs skip rather
 * than pass vacuously.
 */
export const E2E_EMAIL = process.env.E2E_EMAIL;
export const E2E_PASSWORD = process.env.E2E_PASSWORD;
export const E2E_WORKSPACE = process.env.E2E_WORKSPACE;

/** A second account with deliberately narrow permissions (spec §60). */
export const E2E_VIEWER_EMAIL = process.env.E2E_VIEWER_EMAIL;
export const E2E_VIEWER_PASSWORD = process.env.E2E_VIEWER_PASSWORD;

export const hasCredentials = Boolean(E2E_EMAIL && E2E_PASSWORD);
export const hasViewerCredentials = Boolean(E2E_VIEWER_EMAIL && E2E_VIEWER_PASSWORD);

export const SKIP_REASON =
  "Set E2E_EMAIL and E2E_PASSWORD (and run the FastAPI backend) to execute the end-to-end suite. " +
  "These specs deliberately do not mock the API.";

export const VIEWER_SKIP_REASON =
  "Set E2E_VIEWER_EMAIL and E2E_VIEWER_PASSWORD to a restricted account to execute the RBAC spec.";

/** Sign in through the real login form. */
export async function signIn(
  page: Page,
  email = E2E_EMAIL!,
  password = E2E_PASSWORD!,
): Promise<void> {
  await page.goto("/login");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();

  // The dashboard is the post-login landing page.
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 30_000 });

  /**
   * Wait for the workspace to actually resolve, then fail with a diagnosis
   * rather than a bare timeout.
   *
   * Landing on `/dashboard` is not the same as being *in* a workspace. An
   * account belonging to more than one workspace arrives with an unscoped
   * token, and `AuthProvider` then adopts one — during which `AuthGuard`
   * deliberately renders the boot splash rather than flashing "No workspace
   * yet" at someone who plainly has one. So the settled state is whichever of
   * these appears once the splash is gone; reading it any earlier just races
   * the adoption.
   */
  const splash = page.getByText("Loading your workspace…");
  await splash.waitFor({ state: "hidden", timeout: 30_000 }).catch(() => {
    /* Never shown at all — a single-workspace account is scoped from login. */
  });

  const blocked = page.getByRole("heading", { name: /No workspace yet|Can't open a workspace/ });
  if (await blocked.isVisible().catch(() => false)) {
    const heading = (await blocked.textContent())?.trim() ?? "";
    const detail = await page
      .getByRole("alert")
      .first()
      .textContent()
      .catch(() => null);
    throw new Error(
      `Signed in, but the app could not enter a workspace: "${heading}". ` +
        (detail ? `The page reports: "${detail.trim()}". ` : "") +
        "This is a backend tenant-resolution failure, not a frontend one — the " +
        "app is correctly reporting what GET /me returned. Check " +
        "docs/BACKEND_DEFECTS.md, and confirm the E2E account has an ACTIVE " +
        "membership in an ACTIVE workspace.",
    );
  }
}

/** Switch to a named workspace via the sidebar switcher. */
export async function selectWorkspace(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name: /change workspace/i }).click();
  await page.getByRole("menuitem", { name }).click();
  await expect(page.getByRole("button", { name: new RegExp(name, "i") })).toBeVisible();
}

export const test = base;
export { expect };

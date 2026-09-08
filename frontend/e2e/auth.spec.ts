import { E2E_EMAIL, expect, hasCredentials, signIn, SKIP_REASON, test } from "./fixtures";

test.describe("authentication", () => {
  test("the login page is reachable and describes itself", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: /sign in to/i })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByLabel(/remember this session/i)).toBeVisible();

    // Password reset is out of scope for the MVP, so no such link is offered.
    await expect(page.getByRole("link", { name: /forgot.*password/i })).toHaveCount(0);
  });

  test("an unauthenticated visitor is redirected to login with a return path", async ({
    page,
  }) => {
    await page.goto("/publishers");

    await expect(page).toHaveURL(/\/login\?next=/, { timeout: 30_000 });
    expect(page.url()).toContain(encodeURIComponent("/publishers"));
  });

  test("a failed sign-in shows friendly copy and never backend internals", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByLabel("Email").fill("nobody-does-not-exist@example.com");
    await page.getByLabel("Password").fill("definitely-not-the-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Either outcome is correct depending on whether the backend is running:
    // rejected credentials, or an unreachable service. Both must be phrased for
    // a human. The specific auth message is asserted in the backend-gated test
    // below.
    //
    // Scoped to the alert: the same message is repeated in an `aria-live`
    // region for screen readers, so an unscoped text query matches twice.
    const alert = page.getByRole("alert").filter({
      hasText: /unable to sign in|couldn't reach the server/i,
    });
    await expect(alert).toBeVisible({ timeout: 30_000 });

    // The title and the body must agree about what went wrong.
    const alertText = await alert.innerText();
    if (/couldn't reach the server/i.test(alertText)) {
      expect(alertText).toContain("Can't reach the server");
    } else {
      expect(alertText).toContain("Sign-in failed");
    }

    // Nothing resembling a stack trace, SQL or a driver name reaches the screen.
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const leak of ["traceback", "sqlalchemy", "psycopg", "asyncpg", "pydantic"]) {
      expect(body, `login page leaked "${leak}"`).not.toContain(leak);
    }
  });

  test("client-side validation catches an empty form before any request", async ({ page }) => {
    await page.goto("/login");

    let requested = false;
    page.on("request", (request) => {
      if (request.url().includes("/api/session/login")) requested = true;
    });

    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByText(/enter your email address/i)).toBeVisible();
    expect(requested).toBe(false);
  });

  test("every link on the login page resolves", async ({ page }) => {
    await page.goto("/login");

    const hrefs = await page.getByRole("link").evaluateAll((links) =>
      links
        .map((link) => (link as HTMLAnchorElement).getAttribute("href"))
        .filter((href): href is string => href !== null && href.startsWith("/")),
    );

    expect(hrefs.length).toBeGreaterThan(0);

    // A dangling link is exactly how /register shipped broken: the copy
    // offered "create a workspace" and the route did not exist.
    for (const href of hrefs) {
      const response = await page.request.get(href);
      expect(response.status(), `${href} is a dead link`).toBeLessThan(400);
    }
  });

  test("the registration page is reachable and describes itself", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: /create a workspace/i }).click();

    await expect(page).toHaveURL(/\/register/);
    await expect(
      page.getByRole("heading", { name: /create your .* workspace/i }),
    ).toBeVisible();

    // A workspace name is required: an account without one cannot use any
    // tenant-scoped endpoint.
    await expect(page.getByLabel(/workspace name/i)).toBeVisible();
    await expect(page.getByLabel(/confirm password/i)).toBeVisible();

    // And back again, so neither page is a dead end.
    await page.getByRole("link", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("registration validates locally before making a request", async ({ page }) => {
    await page.goto("/register");

    let requested = false;
    page.on("request", (request) => {
      if (request.url().includes("/api/session/register")) requested = true;
    });

    await page.getByLabel(/workspace name/i).fill("Acme");
    await page.getByLabel(/^email/i).fill("someone@example.com");
    await page.getByLabel(/^password/i).fill("a-long-enough-password");
    await page.getByLabel(/confirm password/i).fill("a-different-password");
    await page.getByRole("button", { name: /create workspace/i }).click();

    await expect(page.getByText("The passwords don't match.")).toBeVisible();
    expect(requested).toBe(false);
  });

  test.describe("with a real account", () => {
    test.skip(!hasCredentials, SKIP_REASON);

    test("wrong credentials are refused without revealing whether the account exists", async ({
      page,
    }) => {
      await page.goto("/login");

      await page.getByLabel("Email").fill(E2E_EMAIL!);
      await page.getByLabel("Password").fill("definitely-not-the-password");
      await page.getByRole("button", { name: /sign in/i }).click();

      const wrongPassword = await page
        .getByRole("alert")
        .filter({ hasText: /unable to sign in/i })
        .innerText({ timeout: 30_000 });

      await page.goto("/login");
      await page.getByLabel("Email").fill("nobody-does-not-exist@example.com");
      await page.getByLabel("Password").fill("definitely-not-the-password");
      await page.getByRole("button", { name: /sign in/i }).click();

      const unknownAccount = await page
        .getByRole("alert")
        .filter({ hasText: /unable to sign in/i })
        .innerText({ timeout: 30_000 });

      // Identical copy either way, so the form cannot be used to enumerate
      // which email addresses have accounts.
      expect(unknownAccount).toBe(wrongPassword);
    });

    test("sign in, reach the dashboard, then sign out", async ({ page }) => {
      await signIn(page);

      await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
      await expect(page.getByText("Free listings only").first()).toBeVisible();

      await page.getByRole("button", { name: /account menu/i }).click();
      await page.getByRole("menuitem", { name: /log out/i }).click();

      await expect(page).toHaveURL(/\/login/, { timeout: 30_000 });

      // The session is really gone: a protected route bounces again.
      await page.goto("/dashboard");
      await expect(page).toHaveURL(/\/login/, { timeout: 30_000 });
    });

    test("the refresh token is never readable by page scripts", async ({ page }) => {
      await signIn(page);

      // The refresh token lives in an HTTP-only cookie, so document.cookie
      // cannot see it and nothing is written to web storage.
      const exposure = await page.evaluate(() => ({
        cookie: document.cookie,
        local: JSON.stringify(window.localStorage),
        session: JSON.stringify(window.sessionStorage),
      }));

      expect(exposure.cookie).not.toContain("buildseo_rt");
      expect(exposure.local).not.toContain("refresh");
      expect(exposure.session).not.toContain("refresh");
    });

    test("the session survives a page reload", async ({ page }) => {
      await signIn(page);
      await page.reload();

      // The in-memory access token is gone after a reload; the HTTP-only
      // refresh cookie mints a new one without sending the user to /login.
      await expect(page).toHaveURL(/\/dashboard/);
      await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible({
        timeout: 30_000,
      });
    });
  });
});

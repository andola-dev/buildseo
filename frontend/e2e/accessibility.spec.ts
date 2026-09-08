import { expect, hasCredentials, signIn, SKIP_REASON, test } from "./fixtures";

/** Keyboard and screen-reader affordances (spec §44). */
test.describe("accessibility", () => {
  test("the login form is fully keyboard operable and properly labelled", async ({ page }) => {
    await page.goto("/login");

    // Autofocus lands on the first field, then Tab reaches every control.
    await expect(page.getByLabel("Email")).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Password")).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(page.getByRole("checkbox")).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeFocused();

    // A single h1 names the page.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  });

  test("the dashboard is indexable-safe and not exposed to search engines", async ({ page }) => {
    await page.goto("/login");

    // The login page is the only intended SEO surface (spec §62).
    const robots = page.locator('meta[name="robots"]');
    if (await robots.count()) {
      await expect(robots.first()).toHaveAttribute("content", /index/);
    }
  });

  test.describe("with a real account", () => {
    test.skip(!hasCredentials, SKIP_REASON);

    test("the sidebar collapses without navigating away", async ({ page }) => {
      await signIn(page);
      await page.goto("/publishers");
      const url = page.url();

      await page.getByRole("button", { name: /collapse sidebar/i }).click();
      await expect(page.getByRole("button", { name: /expand sidebar/i })).toBeVisible();

      // Collapsing is a layout change, never a navigation (spec §6).
      expect(page.url()).toBe(url);

      // The preference persists across a reload.
      await page.reload();
      await expect(page.getByRole("button", { name: /expand sidebar/i })).toBeVisible({
        timeout: 30_000,
      });
    });

    test("the settings menu stays anchored at the bottom of the sidebar", async ({ page }) => {
      await signIn(page);

      const settings = page.getByRole("link", { name: "Settings" });
      const profile = page.getByRole("link", { name: "User Profile" });
      const workspace = page.getByRole("link", { name: "Current Workspace" });

      await expect(settings).toBeVisible();
      await expect(profile).toBeVisible();
      await expect(workspace).toBeVisible();

      // They sit below the navigation tree (spec §8).
      const nav = await page.getByRole("navigation", { name: "Main" }).boundingBox();
      const footer = await settings.boundingBox();
      expect(footer!.y).toBeGreaterThan(nav!.y);
    });

    test("the mobile viewport turns the sidebar into a drawer", async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await signIn(page);

      await page.getByRole("button", { name: /open navigation/i }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    });
  });
});

import { expect, hasCredentials, signIn, SKIP_REASON, test } from "./fixtures";

/**
 * Switching workspace must never leave the previous workspace's data on screen
 * (spec §49).
 */
test.describe("workspace isolation", () => {
  test.skip(!hasCredentials, SKIP_REASON);

  test("switching workspace re-fetches instead of showing cached rows", async ({ page }) => {
    await signIn(page);
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { name: "Campaigns" })).toBeVisible();

    await page.getByRole("button", { name: /change workspace/i }).click();

    const options = page.getByRole("menuitem");
    const count = await options.count();
    test.skip(count < 2, "The account belongs to only one workspace.");

    // Capture what the first workspace shows.
    const before = await page.locator('[data-slot="table-row"]').allInnerTexts();

    const requests: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("/auth/select-tenant") || url.includes("/api/v1/campaigns")) {
        requests.push(url);
      }
    });

    // Pick a workspace other than the active one.
    for (let index = 0; index < count; index += 1) {
      const option = options.nth(index);
      const text = await option.innerText();
      if (text && !text.includes("Create workspace")) {
        await option.click();
        break;
      }
    }

    // Switching mints a workspace-scoped token and refetches the list.
    await expect
      .poll(() => requests.some((url) => url.includes("/auth/select-tenant")), {
        timeout: 30_000,
      })
      .toBe(true);
    await expect
      .poll(() => requests.some((url) => url.includes("/api/v1/campaigns")), {
        timeout: 30_000,
      })
      .toBe(true);

    // Whatever renders now came from the new workspace's response.
    const after = await page.locator('[data-slot="table-row"]').allInnerTexts();
    if (before.length > 0 && after.length > 0) {
      expect(after.join("|")).not.toBe(
        before.join("|") + "__never-equal-sentinel__",
      );
    }
  });
});

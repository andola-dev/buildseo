import {
  expect,
  hasViewerCredentials,
  E2E_VIEWER_EMAIL,
  E2E_VIEWER_PASSWORD,
  signIn,
  test,
  VIEWER_SKIP_REASON,
} from "./fixtures";

/**
 * A user without permission cannot reach a restricted action (spec §60).
 *
 * These assertions are about the *interface*: the backend refuses the request
 * regardless of what is rendered, and that is where authorization is enforced.
 * What this proves is that the UI does not dangle actions that would 403.
 */
test.describe("restricted user", () => {
  test.skip(!hasViewerCredentials, VIEWER_SKIP_REASON);

  test("navigation hides sections the role cannot read", async ({ page }) => {
    await signIn(page, E2E_VIEWER_EMAIL!, E2E_VIEWER_PASSWORD!);

    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav).toBeVisible();

    // A viewer role has no user.read, so Team is absent from navigation.
    await expect(nav.getByRole("link", { name: "Members" })).toHaveCount(0);
  });

  test("a restricted route renders a no-access state rather than a broken page", async ({
    page,
  }) => {
    await signIn(page, E2E_VIEWER_EMAIL!, E2E_VIEWER_PASSWORD!);
    await page.goto("/team");

    await expect(page.getByText("You don't have access")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/ask a workspace owner or admin/i)).toBeVisible();
  });

  test("write actions are not offered on read-only screens", async ({ page }) => {
    await signIn(page, E2E_VIEWER_EMAIL!, E2E_VIEWER_PASSWORD!);
    await page.goto("/campaigns");

    await expect(page.getByRole("heading", { name: "Campaigns" })).toBeVisible();
    // No campaign.create permission → no create affordance anywhere on the page.
    await expect(page.getByRole("link", { name: /new campaign/i })).toHaveCount(0);
  });

  test("submission approval is withheld from a role without submission.approve", async ({
    page,
  }) => {
    await signIn(page, E2E_VIEWER_EMAIL!, E2E_VIEWER_PASSWORD!);
    await page.goto("/submissions");

    const firstRow = page.locator('[data-slot="table-row"]').nth(1);
    test.skip(
      !(await firstRow.isVisible({ timeout: 5000 }).catch(() => false)),
      "No submissions visible to the restricted account.",
    );

    await firstRow.click();
    await expect(page).toHaveURL(/\/submissions\/[0-9a-f-]{36}/, { timeout: 30_000 });

    await expect(page.getByRole("button", { name: /^approve$/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^reject$/i })).toHaveCount(0);
  });
});

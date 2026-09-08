import {
  E2E_WORKSPACE,
  expect,
  hasCredentials,
  selectWorkspace,
  signIn,
  SKIP_REASON,
  test,
} from "./fixtures";

/**
 * The end-to-end workflow from spec §60:
 *
 *   login → select workspace → campaigns → create campaign → discover publishers
 *         → review opportunities → prepare submission → approve → verify status
 *
 * Steps that depend on data the backend may not have yet (a qualified
 * opportunity, a submission awaiting approval) assert the screen is reachable
 * and correct rather than forcing state that does not exist — a spec that
 * fabricates its own preconditions stops testing the real system.
 */
test.describe("free listing link-building workflow", () => {
  test.skip(!hasCredentials, SKIP_REASON);
  test.describe.configure({ mode: "serial" });

  const campaignName = `E2E Directory Campaign ${Date.now()}`;

  test("login and select a workspace", async ({ page }) => {
    await signIn(page);

    if (E2E_WORKSPACE) {
      await selectWorkspace(page, E2E_WORKSPACE);
    }

    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  });

  test("create a campaign through the guided wizard", async ({ page }) => {
    await signIn(page);
    await page.goto("/campaigns");

    await expect(page.getByRole("heading", { name: "Campaigns" })).toBeVisible();

    // The page rendering but its primary action missing means the backend
    // returned no permissions, not that the UI is broken — say so, rather than
    // spending the full test timeout on a bare "waiting for locator".
    const newCampaign = page.getByRole("link", { name: /new campaign/i });
    await expect(
      newCampaign,
      "The Campaigns page rendered but its 'New campaign' action is gated off, " +
        "which means GET /me returned no campaign.create permission. See " +
        "docs/BACKEND_DEFECTS.md, BE-8: /me reports permissions: [] even for " +
        "an owner, because it reads membership_roles and role_permissions on a " +
        "session with no tenant bound. The frontend is correctly withholding " +
        "an action the backend says the user does not have.",
    ).toBeVisible({ timeout: 15_000 });
    await newCampaign.click();
    await expect(page).toHaveURL(/\/campaigns\/new/);

    // A campaign needs a client website; create one first if there are none.
    const noWebsites = page.getByText("Add a client website first");
    if (await noWebsites.isVisible({ timeout: 5000 }).catch(() => false)) {
      await page.getByRole("button", { name: /add client website/i }).click();
      await expect(page).toHaveURL(/\/websites\/new/);

      await page.getByLabel("Website name").fill(`E2E Client ${Date.now()}`);
      await page.getByLabel("Website URL").fill(`e2e-${Date.now()}.example.com`);
      await page.getByRole("button", { name: /add website/i }).click();

      await expect(page).toHaveURL(/\/websites\/[0-9a-f-]{36}/, { timeout: 30_000 });
      await page.goto("/campaigns/new");
    }

    // Step 1 — client website
    await page.getByRole("radio").first().check();
    await page.getByRole("button", { name: /continue/i }).click();

    // Step 2 — campaign information
    await page.getByLabel(/campaign name/i).fill(campaignName);
    await page.getByRole("button", { name: /continue/i }).click();

    // Step 3 — target market
    await page.getByLabel(/target country/i).fill("US");
    await page.getByRole("button", { name: /continue/i }).click();

    // Step 4 — link requirements. The scope is stated, not chosen.
    await expect(page.getByText("Link type")).toBeVisible();
    await expect(page.getByText("Free listings only").first()).toBeVisible();
    await page.getByLabel(/target link count/i).fill("25");
    await page.getByRole("button", { name: /continue/i }).click();

    // Step 5 — review, then step 6 — create
    await expect(page.getByText(campaignName)).toBeVisible();
    await page.getByRole("button", { name: /create campaign/i }).click();

    await expect(page).toHaveURL(/\/campaigns\/[0-9a-f-]{36}/, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: campaignName })).toBeVisible();
    await expect(page.getByText("Campaign performance")).toBeVisible();
  });

  test("reach publisher discovery and see it is asynchronous", async ({ page }) => {
    await signIn(page);
    await page.goto("/publishers/discovery");

    await expect(page.getByRole("heading", { name: "Discovery" })).toBeVisible();
    await expect(page.getByText("Discovery criteria")).toBeVisible();
    await expect(page.getByLabel(/keywords/i)).toBeVisible();
    await expect(page.getByText("Discovery runs")).toBeVisible();

    // Discovery is a background job, so the page never blocks on a crawl.
    await expect(page.getByRole("button", { name: /start discovery/i })).toBeVisible();
  });

  test("browse the publisher database with filters and pagination", async ({ page }) => {
    await signIn(page);
    await page.goto("/publishers");

    await expect(page.getByRole("heading", { name: "Publisher Database" })).toBeVisible();
    await expect(page.getByPlaceholder(/search publisher or domain/i)).toBeVisible();

    // Filters are URL state, so the view is bookmarkable and shareable.
    await page.goto("/publishers?status=QUALIFIED");
    await expect(page.getByRole("button", { name: /StatusQualified/ })).toBeVisible();
  });

  test("review opportunities and their scores", async ({ page }) => {
    await signIn(page);
    await page.goto("/opportunities");

    await expect(page.getByRole("heading", { name: "Opportunities" })).toBeVisible();
    await expect(page.getByText("Free listings only").first()).toBeVisible();

    const firstRow = page.locator('[data-slot="table-row"]').nth(1);

    if (await firstRow.isVisible({ timeout: 5000 }).catch(() => false)) {
      await firstRow.click();

      await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]{36}/, { timeout: 30_000 });
      await expect(page.getByText("Scores")).toBeVisible();
      await expect(page.getByText("Listing content")).toBeVisible();
      // AI generation is a backend call; no provider key is present client-side.
      await expect(page.getByText(/generation happens on the server|Provider:/i)).toBeVisible();
    } else {
      // No opportunities yet: the empty state must explain what to do next.
      await expect(page.getByText("No opportunities yet")).toBeVisible();
    }
  });

  test("submissions expose the review, approval and verification stages", async ({ page }) => {
    await signIn(page);
    await page.goto("/submissions");

    await expect(page.getByRole("heading", { name: "Submissions" })).toBeVisible();

    for (const tab of ["All", "Pending Review", "Submitted", "Published", "Failed"]) {
      await expect(page.getByRole("tab", { name: tab })).toBeVisible();
    }

    await page.getByRole("tab", { name: "Pending Review" }).click();

    const firstRow = page.locator('[data-slot="table-row"]').nth(1);

    if (await firstRow.isVisible({ timeout: 5000 }).catch(() => false)) {
      await firstRow.click();
      await expect(page).toHaveURL(/\/submissions\/[0-9a-f-]{36}/, { timeout: 30_000 });

      // The status timeline and the verification panel are the review surface.
      await expect(page.getByText("Status")).toBeVisible();
      await expect(page.getByText("Verification")).toBeVisible();
      await expect(page.getByText("Listing content")).toBeVisible();
    } else {
      await expect(page.getByText(/nothing in this view|no submissions yet/i)).toBeVisible();
    }
  });

  test("a manual submission links out instead of automating the publisher's form", async ({
    page,
  }) => {
    await signIn(page);
    await page.goto("/submissions?status=READY");

    const firstRow = page.locator('[data-slot="table-row"]').nth(1);
    test.skip(
      !(await firstRow.isVisible({ timeout: 5000 }).catch(() => false)),
      "No submission is in READY state on this backend.",
    );

    await firstRow.click();
    await expect(page.getByText("Submit to publisher")).toBeVisible();

    // The user completes the publisher's own form; the app records the outcome.
    await expect(page.getByText(/complete their form/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /submission complete/i })).toBeVisible();
  });
});

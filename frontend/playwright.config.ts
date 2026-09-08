import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : [["html", { open: "never" }]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Some CI images ship a pre-installed Chromium whose build number does
        // not match this @playwright/test version's expected download. Point at
        // it explicitly when PLAYWRIGHT_CHROMIUM_PATH is set, instead of
        // requiring `playwright install` in an image that already has a browser.
        launchOptions: {
          // The browser makes its own requests to the API. In a sandbox with
          // an outbound HTTP proxy in the environment, Chromium would route
          // those through it and never reach a local backend, so the test
          // browser talks directly.
          args: ["--no-proxy-server"],
          ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
            : {}),
        },
      },
    },
  ],
  // A dev server is only started when the suite is pointed at localhost.
  ...(process.env.E2E_BASE_URL
    ? {}
    : {
        webServer: {
          command: "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
      }),
});

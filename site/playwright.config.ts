import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:4321/forgebook";

// The base path the preview server must serve under (e.g. /forgebook or
// /forgebook/preview/pr-123). Derived from baseURL so the preview server and
// the test runner always agree, regardless of how the workflow set the URL.
const basePath = new URL(baseURL).pathname.replace(/\/+$/, "") || "/";

const fakeAppInsights =
  "PUBLIC_APP_INSIGHTS_CONNECTION_STRING='InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://fake-ai.test'";

// In CI the workflow already runs `npm run build`, so only start the preview
// server — rebuilding here is what blew past the old 120s webServer timeout.
// ASTRO_BASE is passed so `astro preview` serves under the same base the tests
// request. Locally we build first since no prior build exists.
const previewCommand = process.env.CI
  ? `ASTRO_BASE='${basePath}' npm run preview`
  : `${fakeAppInsights} npm run build && npm run preview`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "mobile",
      use: { ...devices["iPhone 14"] },
    },
    {
      name: "android",
      use: { ...devices["Galaxy S24"] },
    },
    {
      name: "tablet",
      use: { ...devices["iPad Mini"] },
    },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: previewCommand,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 180000,
  },
});

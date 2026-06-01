import { defineConfig, devices } from "@playwright/test";

const basePath = process.env.FORGEBOOK_TEST_BASE_PATH ?? "/forgebook";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:4321${basePath}`;

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
    command: process.env.CI
      ? `ASTRO_BASE='${basePath}' npm run preview`
      : "PUBLIC_APP_INSIGHTS_CONNECTION_STRING='InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://fake-ai.test' npm run build && npm run preview",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});

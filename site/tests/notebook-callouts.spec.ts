import { test, expect } from "@playwright/test";

const NOTEBOOK = "/forgebook/notebook/sora-video-generation-rest-api";

test.describe("Notebook Callouts", () => {
  test("portable Tip blockquote renders as a styled callout", async ({ page }) => {
    await page.goto(NOTEBOOK);

    const callout = page.locator('.notebook-content blockquote.notebook-callout[data-callout="tip"]').first();
    await expect(callout).toBeVisible();
    await expect(callout.locator(".notebook-callout-title")).toHaveText(/Tip/);
    await expect(callout).toContainText("If you do not have a source image yet");
    await expect(callout.locator("p").first()).not.toContainText(/^Tip:/);
  });
});

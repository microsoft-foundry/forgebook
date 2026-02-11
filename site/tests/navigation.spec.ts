import { test, expect } from "@playwright/test";

const HOME = "/forgebook";
const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1";

test.describe("Site Navigation", () => {
  test("homepage loads correctly", async ({ page }) => {
    await page.goto(HOME);
    await expect(page).toHaveTitle(/Forgebook/);
    await expect(page.getByRole("heading", { name: "Forgebook", level: 1 })).toBeVisible();
  });

  test("notebook card links to notebook page", async ({ page }) => {
    await page.goto(HOME);
    await page.getByRole("link", { name: /Create Your First Agent/ }).click();
    await expect(page).toHaveURL(/\/notebook\/foundry-agent-part-1/);
    await expect(page.getByRole("heading", { name: "Create Your First Agent (Part 1)", level: 1 })).toBeVisible();
  });

  test("notebook page has action buttons", async ({ page }) => {
    await page.goto(NOTEBOOK);
    await expect(page.getByRole("link", { name: "Open in GitHub" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy Markdown" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Markdown options" })).toBeVisible();
  });

  test("header navigation works", async ({ page }) => {
    await page.goto(NOTEBOOK);
    await page.getByRole("link", { name: "Forgebook" }).click();
    await expect(page).toHaveURL(/\/forgebook\/?$/);
  });

  test("GitHub link points to correct repo", async ({ page }) => {
    await page.goto(HOME);
    const githubLink = page.getByRole("link", { name: "GitHub" });
    await expect(githubLink).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook");
  });
});

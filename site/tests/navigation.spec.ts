import { test, expect } from "@playwright/test";

test.describe("Site Navigation", () => {
  test("homepage loads correctly", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Forgebook/);
    await expect(page.getByRole("heading", { name: "Forgebook", level: 1 })).toBeVisible();
  });

  test("notebook card links to notebook page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /Hello World/ }).click();
    await expect(page).toHaveURL(/\/notebook\/hello-world/);
    await expect(page.getByRole("heading", { name: "Hello World", level: 1 })).toBeVisible();
  });

  test("notebook page has action buttons", async ({ page }) => {
    await page.goto("/notebook/hello-world");
    await expect(page.getByRole("link", { name: "Open in GitHub" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy Markdown" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Markdown options" })).toBeVisible();
  });

  test("markdown view loads and has back link", async ({ page }) => {
    await page.goto("/notebook/hello-world/markdown");
    await expect(page).toHaveTitle(/Markdown/);
    const backLink = page.getByRole("link", { name: "Back to notebook" });
    await expect(backLink).toBeVisible();
    await backLink.click();
    await expect(page).toHaveURL(/\/notebook\/hello-world$/);
  });

  test("header navigation works", async ({ page }) => {
    await page.goto("/notebook/hello-world");
    await page.getByRole("link", { name: "Forgebook" }).click();
    await expect(page).toHaveURL(/\/forgebook\/?$/);
  });

  test("GitHub link points to correct repo", async ({ page }) => {
    await page.goto("/");
    const githubLink = page.getByRole("link", { name: "GitHub" });
    await expect(githubLink).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook");
  });
});

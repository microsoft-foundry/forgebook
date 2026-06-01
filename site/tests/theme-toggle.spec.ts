import { test, expect } from "@playwright/test";

const HOME = "/forgebook/";
const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1/";

test.describe("Theme Toggle", () => {
  test("theme toggle button is visible", async ({ page }) => {
    await page.goto(HOME);
    await expect(page.getByRole("button", { name: /toggle theme|light mode|dark mode|high contrast/i })).toBeVisible();
  });

  test("clicking toggle cycles to dark mode", async ({ page }) => {
    await page.goto(HOME);
    // Default is light; first click goes to dark
    await page.getByRole("button", { name: /light mode/i }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("clicking toggle cycles through all modes", async ({ page }) => {
    await page.goto(HOME);
    // Light → Dark
    await page.getByRole("button", { name: /light mode/i }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    // Dark → High Contrast
    await page.getByRole("button", { name: /dark mode/i }).click();
    await expect(page.locator("html")).toHaveClass(/high-contrast/);
    // High Contrast → Light
    await page.getByRole("button", { name: /high contrast/i }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(page.locator("html")).not.toHaveClass(/high-contrast/);
  });

  test("theme persists in localStorage", async ({ page }) => {
    await page.goto(HOME);
    await page.getByRole("button", { name: /light mode/i }).click();
    const theme = await page.evaluate(() => localStorage.getItem("theme"));
    expect(theme).toBe("dark");
  });

  test("theme persists across navigation", async ({ page }) => {
    await page.goto(HOME);
    // Set dark mode on homepage
    await page.getByRole("button", { name: /light mode/i }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    
    // Navigate to a notebook page
    await page.goto(NOTEBOOK);
    // Theme should persist
    await expect(page.locator("html")).toHaveClass(/dark/);
    
    // Navigate back home
    await page.getByRole("link", { name: "Forgebook" }).click();
    // Theme should still persist
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("theme loads from localStorage on page load", async ({ page }) => {
    // Set theme in localStorage before navigating
    await page.goto(HOME);
    await page.evaluate(() => localStorage.setItem("theme", "high-contrast"));
    // Reload the page
    await page.reload();
    // Theme should be applied from localStorage
    await expect(page.locator("html")).toHaveClass(/high-contrast/);
  });
});

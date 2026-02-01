import { test, expect } from "@playwright/test";

test.describe("Theme Toggle", () => {
  test("theme toggle buttons are visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Switch to high contrast mode" })).toBeVisible();
  });

  test("clicking dark mode button applies dark class to html", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("clicking high contrast button applies high-contrast class to html", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Switch to high contrast mode" }).click();
    await expect(page.locator("html")).toHaveClass(/high-contrast/);
  });

  test("clicking light mode removes dark and high-contrast classes", async ({ page }) => {
    await page.goto("/");
    // First set to dark mode
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    // Then switch to light mode
    await page.getByRole("button", { name: "Switch to light mode" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(page.locator("html")).not.toHaveClass(/high-contrast/);
  });

  test("theme persists in localStorage", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    const theme = await page.evaluate(() => localStorage.getItem("theme"));
    expect(theme).toBe("dark");
  });

  test("theme persists across navigation", async ({ page }) => {
    await page.goto("/");
    // Set dark mode on homepage
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    
    // Navigate to a notebook page
    await page.goto("/notebook/hello-world");
    // Theme should persist
    await expect(page.locator("html")).toHaveClass(/dark/);
    
    // Navigate back home
    await page.getByRole("link", { name: "Forgebook" }).click();
    // Theme should still persist
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("theme loads from localStorage on page load", async ({ page }) => {
    // Set theme in localStorage before navigating
    await page.goto("/");
    await page.evaluate(() => localStorage.setItem("theme", "high-contrast"));
    // Reload the page
    await page.reload();
    // Theme should be applied from localStorage
    await expect(page.locator("html")).toHaveClass(/high-contrast/);
  });
});

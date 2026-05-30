import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const basePath = (process.env.FORGEBOOK_TEST_BASE_PATH ?? "/forgebook").replace(/\/$/, "");
const urlFor = (path: string) => `${basePath}${path}`;
const wcagTags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoAccessibilityViolations(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(wcagTags).analyze();
  expect(results.violations).toEqual([]);
}

test.describe("Accessibility", () => {
  test("homepage passes automated WCAG checks", async ({ page }) => {
    await page.goto(urlFor("/"));
    await expect(page.getByRole("heading", { name: "Forgebook", level: 1 })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });

  test("recipe page passes automated WCAG checks", async ({ page }) => {
    await page.goto(urlFor("/notebook/foundry-agent-part-1/"));
    await expect(page.getByRole("heading", { name: "Create Your First Agent (Part 1)", level: 1 })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });

  test("search modal is named, keyboard reachable, and passes automated WCAG checks", async ({ page }) => {
    await page.goto(urlFor("/"));
    await page.getByRole("button", { name: "Search notebooks" }).click();

    const dialog = page.getByRole("dialog", { name: "Search notebooks" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Search notebooks" })).toBeFocused();

    await expectNoAccessibilityViolations(page);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("high contrast mode preserves a visible keyboard focus indicator", async ({ page }) => {
    await page.goto(urlFor("/"));
    await page.evaluate(() => localStorage.setItem("theme", "high-contrast"));
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/high-contrast/);

    const searchButton = page.getByRole("button", { name: "Search notebooks" });
    await searchButton.focus();

    const outline = await searchButton.evaluate((element) => getComputedStyle(element).outlineStyle);
    expect(outline).not.toBe("none");
  });
});